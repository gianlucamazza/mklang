# yaml-language-server: $schema=../schema/mklang.schema.json
# self_consistency.mk — fan-out sampling + majority reducer (§4.7)
#
# Flow: sample_answers (sample: 5, reason) → vote → {END | low_confidence → END}

mklang: "0.2"
machine: self_consistency
entry: sample_answers
budget: 12
default_tier: balanced
result: answer

context:
  question:
    text: "<the question>"

states:
  sample_answers:
    structure: >
      The output is a candidate answer with a one-line justification.
    prompt: |
      Answer the question independently, reasoning step by step:
      {{question.text}}
    reason: true # each branch's chain-of-thought is traced
    sample: 5 # fan-out: 5 independent candidates → a list
    tier: fast
    output: candidates
    gates:
      - when: otherwise
        then: ok
        to: vote

  vote: # reducer (ordinary state) — collapses the list
    structure: >
      The output is the single answer the majority support, stated plainly.
    prompt: |
      Candidate answers:
      {{candidates}}
      Return the answer most of them agree on. If there is no clear majority, say so.
    tier: reasoning
    output: answer
    gates:
      - when: the candidates clearly lack a majority / consensus
        escalate: true
        to: low_confidence
      - when: otherwise
        then: ok
        to: END

  low_confidence:
    structure: >
      The output is the best-effort answer, explicitly flagged as low-confidence.
    prompt: |
      The candidates {{candidates}} lack consensus. Give the best-effort answer and
      flag that confidence is low.
    tier: reasoning
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END
