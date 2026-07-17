# yaml-language-server: $schema=../../../../schema/mklang.schema.json
# std_refine — reflexion / self-refine (SPEC §10: Reflexion)
#
# Flow: draft → {END | repair(2) → draft | escalate → flag_unresolved → END}
# Shows: the repair loop as generate → critique → revise, judged against
# caller-supplied criteria, with a guaranteed-exit design: when both repairs
# are exhausted the repair gate becomes ineligible and the `otherwise`
# escalation routes to a flagging sink — the machine can never dead-end.
# Contract: set `task` (and optionally `criteria`); returns `answer`.

mklang: "0.2"
machine: std_refine
entry: draft
budget: 6 # draft ×3 (initial + 2 repairs) + sink, with headroom
default_tier: balanced
result: answer

context:
  task: "<the task>"
  criteria: "clear, correct, and complete" # override with --set criteria="…"

states:
  draft:
    structure: >
      Reads {{task}} and {{criteria}}. The output is the full answer to the
      task; each revisit must fix the cited shortfall, not start over.
    prompt: |
      Task: {{task}}

      Produce the best possible answer. It will be judged against these
      criteria: {{criteria}}.
    output: answer
    gates:
      - when: the answer satisfies every criterion listed under the context key 'criteria'
        then: ok
        to: END
      - when: the answer falls short of one or more of the criteria
        repair: 2 # re-run draft with the failed condition as feedback
        to: draft
      - when: otherwise # repairs exhausted (or judge undecided) — flag, don't fail
        escalate: true
        to: flag_unresolved

  flag_unresolved: # escalation sink — best effort, honestly labelled
    structure: >
      Reads {{task}}, {{criteria}} and the last {{answer}}. The output is the
      best available answer with a plain note on which criteria remain unmet.
    prompt: |
      Repair attempts are exhausted. Present the best available answer to the
      task {{task}} based on this last attempt:
      {{answer}}
      Append one plain sentence flagging which of the criteria ({{criteria}})
      it may still miss.
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END
