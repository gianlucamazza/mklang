# yaml-language-server: $schema=../schema/mklang.schema.json
# research_web.mk — iterative research with a real `tool: search` state (ADR 0016)
#
# Flow: plan_query → search → check_sufficiency → {loop | finalize}
#
# Offline: `search` is a structured stub unless the host binds a backend
# (MKLANG_SEARCH_BACKEND=fake|tavily, or mklang.search.configure_search).
# Web observations are untrusted context (SPEC §11).
#
# Scenario-tested: `mklang test examples/research_web.mk --script examples/research_web.test.yaml`

mklang: "0.3"
machine: research_web
entry: plan_query
budget: 14
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
  notes: [] # accumulates search observations (tool results)

states:
  plan_query:
    structure: >
      A single concise web search query for the open research question,
      informed by notes so far. Output ONLY the query string.
    prompt: |
      Research question: {{question.text}}
      Notes so far: {{notes}}
      Write ONE search query that would fill the biggest gap in the notes.
      If notes are empty, start with the core of the question.
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
      States whether the notes are enough to answer the question completely,
      with a one-line reason.
    prompt: |
      Question: {{question.text}}
      Notes (search observations): {{notes}}
      Are these notes sufficient for a grounded answer? What is still missing?
    tier: fast
    output: verdict
    gates:
      - when: the notes are sufficient to answer the question completely
        then: ok
        to: finalize
      - when: key information is still missing and another search is worthwhile
        then: ok
        to: plan_query
      - when: otherwise
        then: ok
        to: finalize

  finalize:
    structure: >
      A cited answer grounded only in the notes; flag uncertainty.
    prompt: |
      Answer {{question.text}} using only these search notes:
      {{notes}}
      Cite titles/URLs from the notes. If evidence is thin, say so.
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
