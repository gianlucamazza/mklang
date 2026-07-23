# yaml-language-server: $schema=../../../../schema/mklang.schema.json
# std_plan_execute — plan, execute each step, combine (SPEC §10: Plan-and-Execute)
#
# Flow: plan (parse: list) → execute (over: {{steps}}) → combine → {END | repair(1)}
# Shows: `parse: list` (0.3) turning the planner's JSON array into a real list
# that `over:` fans out over — the pattern that needed structured output. An
# unparseable plan halts cleanly with state-error: parse-list (never garbage).
# Contract: set `task`; returns `answer`.

mklang: "0.3"
machine: std_plan_execute
entry: plan
budget: 16 # plan + one step per item + combine; sized for plans up to ~12 steps
default_tier: balanced
result: answer

context:
  task: "<the task>"

states:
  plan:
    structure: >
      A JSON array of 2 to 6 short, self-contained step strings — nothing else,
      no prose around it.
    prompt: |
      Break this task into an ordered plan of 2-6 concrete steps, and output
      ONLY the JSON array of step strings:
      {{task}}
    tier: reasoning
    parse: list # 0.3: the deposited value is a real list, ready for over:
    output: steps
    gates:
      - when: otherwise
        then: ok
        to: execute

  execute:
    over: "{{steps}}"
    structure: >
      The output is the result of carrying out this single step, self-contained.
    prompt: |
      Overall task: {{task}}

      Carry out step {{index}} of the plan: {{item}}
    tier: fast # one branch per step
    output: results
    gates:
      - when: otherwise
        then: ok
        to: combine

  combine: # reducer
    structure: >
      Reads {{task}}, {{steps}} and {{results}}. The output is the final answer
      assembled from the step results.
    prompt: |
      Step results:
      {{results}}

      Assemble them into the final answer to the task {{task}}, in plan order.
    tier: reasoning
    output: answer
    gates:
      - when: the answer covers every step's result
        then: ok
        to: END
      - when: one or more step results were dropped
        repair: 1
        to: combine
      - when: otherwise
        then: ok
        to: END
