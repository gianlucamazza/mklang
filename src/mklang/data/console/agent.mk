# yaml-language-server: $schema=../../../../schema/mklang.schema.json
# agent.mk — the console's brain (ADR 0015): one run per user turn.
#
# Flow: decide → {discover | prepare_run → do_run | clarify | reply → END}
#       (every action loops back to decide; the budget bounds the turn)
# Shows: the console's intelligence as an ordinary, auditable machine — swap it
# with `mklang console --agent your_brain.mk` as long as the tool contract
# (list_machines / run_machine / ask_user, console-registered) is honored.
# Contract: the console sets `user_message` and `history`; observations
# accumulate under `observation`; the turn's answer lands in `reply`.

mklang: "0.3"
machine: console_agent
entry: decide
budget: 12 # ~5 decide/action cycles + the reply
default_tier: balanced
result: reply

tools:
  - name: list_machines
    description: >
      The catalog of commissionable machines (console-registered).
      Input: {} — returns JSON rows with name, result, budget, context keys.
  - name: run_machine
    description: >
      Commission a machine and return its outcome as JSON.
      Input: {"request": '{"target": "...", "inputs": {...}}'} — the console
      brokers HITL escalations to the human and streams live events.
  - name: ask_user
    description: >
      Ask the human one question and return the reply.
      Input: {"question": "..."}.

context:
  user_message: ""
  history: "" # prior turns, supplied by the console session
  observation: [] # tool observations of THIS turn (accumulated)

states:
  decide: # the ReAct "think" step
    structure: >
      One line starting with exactly one of DISCOVER, RUN, CLARIFY or REPLY,
      followed by the details: for RUN the machine name and the inputs to pass;
      for CLARIFY the question to ask the user; for REPLY the substance of the
      answer.
    prompt: |
      You are the mklang console agent. You satisfy the user's request by
      commissioning machines (self-contained LLM state machines) and reporting
      results honestly.

      Conversation so far: {{history}}
      User request: {{user_message}}
      Observations this turn: {{observation}}

      Choose the single next action:
      - DISCOVER — list the available machines (only if you don't already know
        a suitable one from the observations).
      - RUN — commission a machine now: name it and spell out its inputs.
      - CLARIFY — ask the user one precise question you cannot answer yourself.
      - REPLY — the request is satisfied (or answerable directly): state the
        substance of the final answer.
    tier: reasoning
    reason: true
    output: thought
    gates:
      - when: the output chooses DISCOVER
        then: ok
        to: discover
      - when: the output chooses RUN
        then: ok
        to: prepare_run
      - when: the output chooses CLARIFY
        then: ok
        to: clarify
      - when: the output chooses REPLY
        then: ok
        to: reply
      - when: otherwise
        then: ok
        to: reply

  discover:
    tool: list_machines
    output: observation
    accumulate: true
    gates:
      - when: otherwise
        then: ok
        to: decide

  prepare_run: # thought → one JSON blob the run tool consumes verbatim
    structure: >
      A JSON object {"target": "<machine name>", "inputs": {<context key>:
      <value>, ...}} and nothing else. Values may be strings, numbers or lists.
    prompt: |
      Turn this decision into the run request JSON:
      {{thought}}
    tier: fast
    output: run_request
    gates:
      - when: otherwise
        then: ok
        to: do_run

  do_run: # the ReAct "act" step
    tool: run_machine
    input:
      request: "{{run_request}}"
    output: observation
    accumulate: true
    gates:
      - when: otherwise
        then: ok
        to: decide

  clarify:
    tool: ask_user
    input:
      question: "{{thought}}"
    output: observation
    accumulate: true
    gates:
      - when: otherwise
        then: ok
        to: decide

  reply:
    structure: >
      The final answer for the user: plain, complete, and honest about what was
      run and what it returned (or why nothing needed to run).
    prompt: |
      User request: {{user_message}}
      Your decision: {{thought}}
      Observations this turn: {{observation}}

      Write the final reply to the user.
    output: reply
    gates:
      - when: otherwise
        then: ok
        to: END
