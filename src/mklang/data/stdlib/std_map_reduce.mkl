# yaml-language-server: $schema=../../../../schema/mklang.schema.json
# std_map_reduce — generic map over items + reduce (SPEC §10: Map-Reduce)
#
# Flow: map (over: {{items}}) → reduce → {END | repair(1) → reduce}
# Shows: purely generative map-reduce — one fast-tier branch per item applying
# {{item_task}}, then a reasoning-tier reducer applying {{reduce_task}}.
# `items` must be a real list: override via --set items='["…","…"]' (JSON) or
# an MCP list input. An empty list is handled: map deposits [] and the reducer
# states plainly that there was nothing to process.
# Contract: set `task` + `items` (and optionally `item_task`/`reduce_task`);
# returns `answer`.

mklang: "0.2"
machine: std_map_reduce
entry: map
budget: 20 # over charges len(items) steps — size ≥ len(items) + 3
default_tier: balanced
result: answer

context:
  task: "<the overall task>"
  items: # the host supplies the real list; placeholders keep check/lint green
    - "<item 1>"
    - "<item 2>"
  item_task: "process the item faithfully"
  reduce_task: "combine the results into one coherent answer"

states:
  map:
    over: "{{items}}"
    structure: >
      The output is the result of applying the per-item instruction to this
      single item, self-contained.
    prompt: |
      Overall task: {{task}}

      Apply this instruction to the single item below (item {{index}}): {{item_task}}

      Item:
      {{item}}
    tier: fast # high-volume branches
    output: results
    gates:
      - when: otherwise
        then: ok
        to: reduce

  reduce: # reducer (ordinary state)
    structure: >
      Reads {{task}}, {{reduce_task}} and the per-item {{results}}. The output
      is the final combined answer.
    prompt: |
      Per-item results:
      {{results}}

      Combine them as instructed - {{reduce_task}} - into the final answer to
      the overall task {{task}}. If there are no per-item results, say plainly
      that there was nothing to process.
    tier: reasoning
    output: answer
    gates:
      - when: the combined answer accounts for every per-item result
        then: ok
        to: END
      - when: one or more per-item results were dropped or contradicted
        repair: 1
        to: reduce
      - when: otherwise
        then: ok
        to: END
