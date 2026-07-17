# yaml-language-server: $schema=../schema/mklang.schema.json
# research_compress.mk — research loop with explicit working-memory compression
# (ADR 0017 Layer 1). Same tool:search contract as research_web.mk, plus a
# compress_notes state that rewrites notes short before another search round.
#
# Flow: plan → search → check → {compress → plan | finalize}
#
# Scenario-tested:
#   mklang test examples/research_compress.mk --script examples/research_compress.test.yaml

mklang: "0.3"
machine: research_compress
entry: plan_query
budget: 18
default_tier: balanced
result: answer

tools:
  - name: search
    description: >
      Web search. Input: {"query": "…", "max_results"?: 5}.
      Returns JSON {query, results:[{title,url,snippet}], error}.

context:
  question:
    text: "<the research question>"
  notes: [] # accumulates search observations; may be rewritten by compress_notes

states:
  plan_query:
    structure: >
      A single concise web search query for the open research question,
      informed by notes so far. Output ONLY the query string.
    prompt: |
      Research question: {{question.text}}
      Working notes: {{notes}}
      Write ONE search query that would fill the biggest gap.
    tier: fast
    output: query
    gates:
      - when: otherwise
        then: ok
        to: search

  search:
    tool: search
    input: { query: "{{query}}", max_results: 5 }
    accumulate: true
    output: notes
    gates:
      - when: otherwise
        then: ok
        to: check_sufficiency

  check_sufficiency:
    structure: >
      States whether notes are enough to answer completely, or whether they
      should be compressed before another search (too long / noisy), or whether
      another search is needed with notes as they are.
    prompt: |
      Question: {{question.text}}
      Notes: {{notes}}
      Decide: (1) enough to answer, (2) notes are too long/noisy and should be
      compressed before more research, or (3) need another search with notes as-is.
    tier: fast
    output: verdict
    gates:
      - when: the notes are sufficient to answer the question completely
        then: ok
        to: finalize
      - when: the notes are too long or noisy and should be compressed first
        then: ok
        to: compress_notes
      - when: key information is still missing and another search is worthwhile
        then: ok
        to: plan_query
      - when: otherwise
        then: ok
        to: finalize

  compress_notes:
    structure: >
      A short bullet list (max ~8 lines) of durable facts from the notes,
      dropping duplicates and low-value snippets. Plain text, not JSON.
    prompt: |
      Compress these research notes into a tight working memory for later
      searches and the final answer. Keep only facts, titles, and URLs that
      matter for: {{question.text}}

      Notes:
      {{notes}}
    tier: fast
    output: notes
    gates:
      - when: otherwise
        then: ok
        to: plan_query

  finalize:
    structure: >
      A cited answer grounded only in the notes; flag uncertainty.
    prompt: |
      Answer {{question.text}} using only these notes:
      {{notes}}
      Cite sources. If evidence is thin, say so.
    tier: reasoning
    output: answer
    gates:
      - when: the answer is grounded in the notes and cites them
        then: ok
        to: END
      - when: the answer invents facts not present in the notes
        repair: 1
        to: finalize
      - when: otherwise
        then: ok
        to: END
