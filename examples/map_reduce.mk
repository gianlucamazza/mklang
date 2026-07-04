# yaml-language-server: $schema=../schema/mklang.schema.json
# map_reduce.mk — orchestrator-worker (§4.7 over + §4.8 call)
#
# Flow: map (one summarize_doc sub-run per chunk) → combine → END
# The callee `summarize_doc` lives in summarize_doc.mk (same project dir).

mklang: "0.2"
machine: map_reduce
entry: map
budget: 20
default_tier: balanced
result: summary

context:
  chunks: [] # list of text chunks; the host supplies them

states:
  map: # fan-out over the list, each item handled by a sub-machine
    over: "{{chunks}}"
    call: summarize_doc
    input: { text: "{{item}}" }
    output: summaries
    gates:
      - when: otherwise
        then: ok
        to: combine

  combine: # reducer
    structure: >
      The output is one consolidated summary with duplicates removed.
    prompt: |
      Merge these per-chunk summaries into one coherent summary:
      {{summaries}}
    tier: reasoning
    output: summary
    gates:
      - when: otherwise
        then: ok
        to: END
