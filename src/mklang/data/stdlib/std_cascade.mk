# yaml-language-server: $schema=../../../../schema/mklang.schema.json
# std_cascade — speculative cascade: cheap first, strong on demand (SPEC §10)
#
# Flow: draft (fast) → {END | escalate → deliberate (reasoning) → END}
# Shows: tier routing as a cost control — most tasks end at the fast tier; only
# low-confidence drafts pay for the reasoning tier. BOTH paths deposit under
# the same `answer` key, so the caller's contract is identical either way.
# Contract: set `task`; returns `answer`.

mklang: "0.2"
machine: std_cascade
entry: draft
budget: 4 # longest path is 2 states; headroom keeps `mklang check` quiet
default_tier: balanced
result: answer

context:
  task: "<the task>"

states:
  draft:
    structure: >
      Reads {{task}}. The output is a best-effort answer plus one final line
      self-rating its confidence (high / medium / low) with a reason.
    prompt: |
      Answer the task directly and efficiently, then add ONE final line rating
      your confidence (high / medium / low) and why:
      {{task}}
    tier: fast
    output: answer
    gates:
      - when: the draft fully and correctly answers the task
        then: ok
        to: END
      - when: otherwise # not confident enough — promote to the strong tier
        escalate: true
        to: deliberate

  deliberate:
    structure: >
      Reads {{task}} and the fast {{answer}}. The output is a careful, verified
      answer that replaces the draft under the same key.
    prompt: |
      The quick draft below was not confident enough. Answer rigorously,
      checking your work step by step, and correct the draft wherever it is
      wrong.
      Task: {{task}}
      Draft: {{answer}}
    tier: reasoning
    reason: true
    output: answer # same key as draft — both paths produce the result
    gates:
      - when: otherwise
        then: ok
        to: END
