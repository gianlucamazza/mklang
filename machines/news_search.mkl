# yaml-language-server: $schema=../schema/mklang.schema.json
# Workspace machine: web news via host tool `search` (not generative fiction).
# Requires a bound search backend (TAVILY_API_KEY auto-enables Tavily).
# Host fills empty context.today (ISO date) when declared — no language magic.

mklang: "0.3"
machine: news_search
entry: plan_query
budget: 10
default_tier: balanced
result: answer

tools:
  - name: search
    description: >
      Web search. Input: {"query": "…", "max_results"?: 5, "days"?: N,
      "topic"?: "news"|"general"}. Returns JSON
      {tool, stub, error, query, results:[{title,url,snippet,published_date?}]}.

context:
  topic: ""
  today: "" # host fills ISO date when empty
  notes: []
  query: ""
  answer: ""

states:
  plan_query:
    structure: One concise web search query string only.
    prompt: |
      Today is {{today}}.
      Topic: {{topic}}
      Write ONE web search query for recent news about this topic.
      Prefer current/recent coverage; include the year from today when helpful.
      Output ONLY the query text.
    tier: fast
    output: query
    gates:
      - when: otherwise
        then: ok
        to: search

  search:
    tool: search
    input: { query: "{{query}}", max_results: 5, days: 30, topic: news }
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
      Today is {{today}}.
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
      Today is {{today}}.
      Topic: {{topic}}
      Notes: {{notes}}
      Explain honestly that no web results were available. If the notes say
      search is not bound, tell the user to set TAVILY_API_KEY (or
      MKLANG_SEARCH_BACKEND=tavily|fake). Do not invent news from training knowledge.
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END

  finalize:
    structure: >
      A short news brief grounded only in the notes, with titles and URLs.
    prompt: |
      Today is {{today}}.
      Summarize recent news about {{topic}} using ONLY these search notes:
      {{notes}}
      List items with title, one-line gist, URL, and published_date when present.
      Prefer more recent items. Flag uncertainty.
      Do not invent stories not present in the notes. Do not fill gaps with
      pre-training knowledge or facts that stop at an older year than today.
      If notes are partial or the observation reported truncation, say so.
    tier: reasoning
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END
