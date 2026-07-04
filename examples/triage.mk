# yaml-language-server: $schema=../schema/mklang.schema.json
# triage.mk — branching FSM (customer support)
#
# Flow:
#   classify → {bug | billing | other} → gather → draft_reply → {send | human_review}
# Shows: branching on gates, a repair loop, escalate to human review.

mklang: "0.2"
machine: triage
entry: classify
budget: 25
default_tier: balanced # provider-neutral; the runtime maps tiers to concrete models

# Initial blackboard values. In a real run the host supplies these.
context:
  ticket:
    body: "<the customer ticket text>"

states:
  # --- Classify the ticket into a category -------------------------------
  classify:
    structure: >
      Reads {{ticket.body}}. The output is one of "bug", "billing", "other",
      with a short justification.
    prompt: |
      Classify the following ticket as "bug", "billing" or "other".
      Ticket: {{ticket.body}}
    tier: fast # a simple classification — no need for the strongest model
    output: category
    gates:
      - when: the category is "bug"
        then: ok
        to: gather
      - when: the category is "billing"
        then: ok
        to: gather
      - when: otherwise
        then: ok
        to: gather

  # --- Gather facts from the knowledge base ------------------------------
  gather:
    structure: >
      Reads {{ticket.body}} and {{category}}. The output is the relevant facts
      found in the KB, or a note that nothing was found.
    prompt: |
      Search the KB for information to answer a ticket of category
      {{category}}: {{ticket.body}}. Report only facts present in the KB.
    execution: |
      You may use the `search_kb` tool at most 3 times.
      Do not invent information that is not in the KB.
    output: kb_answer
    gates:
      - when: enough facts were found to answer the ticket
        then: ok
        to: draft_reply
      - when: the KB contains nothing useful for this ticket
        escalate: true
        to: human_review
      - when: otherwise
        then: ok
        to: draft_reply

  # --- Draft the reply ---------------------------------------------------
  draft_reply:
    structure: >
      Reads {{ticket.body}} and {{kb_answer}}. The output is an email reply to
      the customer, courteous tone, max 150 words.
    prompt: |
      Write a reply to {{ticket.body}} using the facts in {{kb_answer}}.
      Do not invent policies that are not in the KB.
    execution: |
      Do not contact the customer here: in this state you only draft.
    tier: reasoning # customer-facing prose + policy care — use the strongest model
    output: draft
    gates:
      - when: the draft resolves the request and is in the required courteous tone
        then: ok
        to: send
      - when: the draft is missing information that should have come from the KB
        repair: 2
        to: gather
      - when: the draft is not in the required tone or is incomplete
        repair: 2
        to: draft_reply
      - when: the request implies a refund over threshold or a legal matter
        escalate: true
        to: human_review
      - when: otherwise
        escalate: true
        to: human_review

  # --- Send (terminal success state) -------------------------------------
  send:
    structure: >
      Reads {{draft}}. The output is a confirmation the reply was sent.
    prompt: |
      Send the reply {{draft}} to the customer and confirm it was sent.
    output: sent
    gates:
      - when: the send is confirmed
        then: ok
        to: END
      - when: otherwise
        fail: true

  # --- Human review (escalation handler) ---------------------------------
  human_review:
    structure: >
      The output is a summary of the case and the escalation reason for a
      human operator.
    prompt: |
      Summarize the ticket {{ticket.body}}, the category {{category}} and the
      draft {{draft}} (if present) for handoff to a human operator.
    output: handoff
    gates:
      - when: otherwise # the summary is prepared for the operator, then finish
        then: ok
        to: END
