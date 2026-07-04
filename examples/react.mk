# yaml-language-server: $schema=../schema/mklang.schema.json
# react.mk — ReAct loop: reason → act → observe, accumulating a scratchpad (§4.5/§4.6)
#
# Flow: step → {finalize | observe → step} ; the global budget bounds the loop.

mklang: "0.2"
machine: react
entry: step
budget: 15
default_tier: balanced
result: answer

context:
  question:
    text: "<the question>"
  scratchpad: "" # accumulates thought / action / observation across the loop

states:
  step:
    structure: >
      The output is EITHER "ACTION: <tool>(<args>)" to gather information, OR
      "ANSWER: <final answer>" when enough is known to conclude.
    prompt: |
      Question: {{question.text}}
      Work so far:
      {{scratchpad}}
      Decide the single next step.
    execution: |
      Available tool: search(query) — returns web snippets. Use it when you lack a
      fact. Take exactly one action per step; never fabricate observations.
    reason: true
    accumulate: true # the thought/decision is appended to the scratchpad list
    output: scratchpad
    gates:
      - when: the output is a final ANSWER
        then: ok
        to: finalize
      - when: the output is an ACTION (more information is needed)
        then: ok
        to: observe
      - when: otherwise
        then: ok
        to: observe

  observe:
    structure: >
      The output is the observation returned by the tool for the most recent action.
    prompt: |
      Execute the most recent action in {{scratchpad}} and report ONLY the observation.
    execution: |
      If no real tool is bound, faithfully simulate the `search` result.
    accumulate: true # the observation is appended to the scratchpad list
    output: scratchpad
    gates:
      - when: otherwise
        then: ok
        to: step

  finalize:
    structure: >
      The output is the final answer to the question.
    prompt: "Based on {{scratchpad}}, give the final answer to: {{question.text}}"
    tier: reasoning
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END
