# yaml-language-server: $schema=../../../../schema/mklang.schema.json
# std_cot — chain-of-thought (SPEC §10: Chain-of-Thought)
#
# Flow: solve → END
# Shows: `reason: true` as a first-class primitive — the step-by-step working is
# elicited privately and recorded in the trace; only the clean answer lands in
# context. Contract: set `task` (--set task="…" or MCP input); reads {{task}},
# returns `answer`.

mklang: "0.2"
machine: std_cot
entry: solve
budget: 3 # single state; headroom so `mklang check` stays quiet
default_tier: balanced
result: answer

context:
  task: "<the task>"

states:
  solve:
    structure: >
      Reads {{task}}. The output is the final answer only, concise and complete;
      the step-by-step working stays in the private reasoning.
    prompt: |
      Task: {{task}}

      Think the task through step by step, then state the final answer.
    reason: true # the chain-of-thought is traced, never deposited into context
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END
