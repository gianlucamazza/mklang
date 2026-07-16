# yaml-language-server: $schema=../schema/mklang.schema.json
# research.mk — looping FSM (iterative Q&A)
#
# Flow:
#   gather → check_sufficiency → {loop back to gather | finalize} → END
# Shows: a loop, a sufficiency gate, and the global budget forcing termination.
#
# gather is generative only: it does not call host tools. For real search I/O
# use a `tool:` state (see react.mk / triage.mk) — do not put tool names in
# `execution` on generative states (the model cannot invoke them).

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
      From your training knowledge only, add NEW candidate facts not already in
      the notes. Label each as uncertain if not sure. If nothing new, say so.
    execution: |
      No host tools are available in this state. Do not claim you searched the web.
      Do not invent URLs or citations you cannot support. Prefer "unknown" over fiction.
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
