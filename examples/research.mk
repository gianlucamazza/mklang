# yaml-language-server: $schema=../schema/mklang.schema.json
# research.mk — looping FSM (iterative Q&A)
#
# Flow:
#   gather → check_sufficiency → {loop back to gather | finalize} → END
# Shows: a loop, a sufficiency gate, and the global budget forcing termination.

mklang: "0.2"
machine: research
entry: gather
budget: 12 # caps the gather↔check loop; the run cannot diverge

context:
  question:
    text: "<the research question>"
  notes: "" # accumulates across gather iterations

states:
  # --- Collect one round of evidence -------------------------------------
  gather:
    structure: >
      Reads {{question.text}} and the running {{notes}}. The output is the
      previous notes extended with new evidence from this round.
    prompt: |
      Research question: {{question.text}}
      Notes so far: {{notes}}
      Find NEW evidence not already in the notes and append it. If you find
      nothing new, say so explicitly.
    execution: |
      You may use the `web_search` tool at most 2 times per round.
      Cite each fact with its source. Do not repeat facts already in notes.
    output: notes
    gates:
      - when: new evidence was added this round
        then: ok
        to: check_sufficiency
      - when: otherwise # no new evidence — still proceed to the sufficiency check
        then: ok
        to: check_sufficiency

  # --- Decide whether the evidence is enough -----------------------------
  check_sufficiency:
    structure: >
      Reads {{question.text}} and {{notes}}. The output states whether the notes
      are sufficient to answer the question completely, with a reason.
    prompt: |
      Given the notes {{notes}}, can the question {{question.text}} now be
      answered completely and accurately? Explain what, if anything, is still
      missing.
    tier: fast # a yes/no sufficiency check
    output: verdict
    gates:
      - when: the notes are sufficient to answer the question completely
        then: ok
        to: finalize
      - when: key information is still missing and more research is worthwhile
        then: ok
        to: gather # loop; the global budget guarantees termination
      - when: otherwise
        then: ok
        to: finalize # give up looping, answer with what we have

  # --- Produce the final answer (terminal) -------------------------------
  finalize:
    structure: >
      Reads {{question.text}} and {{notes}}. The output is a cited answer to the
      question, flagging any remaining uncertainty.
    prompt: |
      Write the final answer to {{question.text}} using only {{notes}}.
      Cite sources. If some aspect is still uncertain, state it plainly.
    tier: reasoning # the synthesis step — use the strongest model
    output: answer
    gates:
      - when: the answer is grounded in the notes and cites its sources
        then: ok
        to: END
      - when: the answer makes claims not supported by the notes
        repair: 1
        to: finalize
      - when: otherwise
        then: ok
        to: END
