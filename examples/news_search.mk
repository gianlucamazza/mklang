# yaml-language-server: $schema=../schema/mklang.schema.json
# Workspace machine: web news via host tool `search` (not generative fiction).
# Requires a bound search backend (TAVILY_API_KEY auto-enables Tavily).

mklang: "0.3"
machine: news_search
entry: plan_query
budget: 10
default_tier: balanced
result: answer

tools:
  - name: search
    description: >
      Web search. Input: {"query": "…", "max_results"?: 5}.
      Returns JSON {query, results:[{title,url,snippet}], error}.

context:
  topic: ""
  notes: []
  query: ""
  answer: ""

states:
  plan_query:
    structure: One concise web search query string only.
    prompt: |
      Topic: {{topic}}
      Write ONE web search query for recent news about this topic.
      Output ONLY the query text.
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
        to: check

  check:
    structure: >
      Whether the search notes contain usable news items, or are empty/errors.
    prompt: |
      Topic: {{topic}}
      Search notes: {{notes}}
      Are there usable news items with titles/URLs?
    tier: fast
    output: verdict
    gates:
      - when: the notes contain usable news items with titles or URLs
        then: ok
        to: finalize
      - when: the notes are empty or report that no external search is bound
        then: ok
        to: no_search
      - when: otherwise
        then: ok
        to: no_search

  no_search:
    structure: A clear explanation that web search was unavailable or empty.
    prompt: |
      Topic: {{topic}}
      Notes: {{notes}}
      Explain honestly that no web results were available. If the notes say
      search is not bound, tell the user to set TAVILY_API_KEY (or
      MKLANG_SEARCH_BACKEND=tavily|fake). Do not invent news.
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END

  finalize:
    structure: >
      A short news brief grounded only in the notes, with titles and URLs.
    prompt: |
      Summarize recent news about {{topic}} using ONLY these search notes:
      {{notes}}
      List items with title, one-line gist, and URL. Flag uncertainty. Do not
      invent stories not present in the notes.
    tier: reasoning
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END
