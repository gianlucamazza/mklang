# yaml-language-server: $schema=../../../../schema/mklang.schema.json
# std_debate — multi-persona debate + synthesis (SPEC §10: Debate / ensemble)
#
# Flow: argue (over: {{personas}}) → synthesize → {END | repair(1) → synthesize}
# Shows: `over` fan-out with one branch per persona ({{item}} = the persona,
# {{index}} = seat number), a reasoning-tier synthesizer, and a coverage
# repair gate. `personas` must be a real list: override via --set
# personas='["…","…"]' (JSON) or an MCP list input — never through call: input.
# Contract: set `task` (and optionally `personas`); returns `answer`.

mklang: "0.2"
machine: std_debate
entry: argue
budget: 12 # over charges len(personas) steps — size ≥ len(personas) + 3
default_tier: balanced
result: answer

context:
  task: "<the task>"
  personas: # one debater per entry; generic, domain-free defaults
    - "a strong advocate for the most promising option"
    - "a rigorous skeptic hunting for flaws and risks"
    - "a pragmatist focused on cost, effort, and workability"

states:
  argue:
    over: "{{personas}}"
    structure: >
      The output is this persona's position on the task: a stance, its two or
      three best arguments, and what the other perspectives get wrong.
    prompt: |
      Task under debate: {{task}}

      You are debater {{index}}, arguing as {{item}}. Make the strongest case
      from this perspective only: state your position, give your best
      arguments, and say what the other perspectives are likely to get wrong.
    tier: fast # high-volume branches — the synthesis carries the quality
    output: positions
    gates:
      - when: otherwise
        then: ok
        to: synthesize

  synthesize: # reducer — the debate collapses into one answer
    structure: >
      Reads {{task}} and {{positions}}. The output is the final answer: the
      position that best survives the debate, with the strongest objection
      acknowledged.
    prompt: |
      Debate positions:
      {{positions}}

      Synthesize the debate into one final answer to the task {{task}}: weigh
      the arguments against each other, keep what survives scrutiny, and
      acknowledge the strongest surviving objection.
    tier: reasoning
    reason: true
    output: answer
    gates:
      - when: the synthesis weighs every debated perspective and answers the task
        then: ok
        to: END
      - when: the synthesis ignores one or more of the debated perspectives
        repair: 1
        to: synthesize
      - when: otherwise
        then: ok
        to: END
