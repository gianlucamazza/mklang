# yaml-language-server: $schema=../../../../schema/mklang.schema.json
# agent.mk — the console's brain (ADR 0015): one run per user turn.
#
# Flow: decide → {discover | prepare_run → do_run | clarify |
#                 author → save | reply → END}
#       (every action loops back to decide; the budget bounds the turn)
# Shows: the console's intelligence as an ordinary, auditable machine — swap it
# with `mklang console --agent your_brain.mk` as long as the tool contract
# (list_machines / run_machine / ask_user, console-registered) is honored.
# Contract: the console sets `user_message` and `history`; observations
# accumulate under `observation`; the turn's answer lands in `reply`.

mklang: "0.3"
machine: console_agent
entry: decide
budget: 16 # decide/action cycles incl. an authoring repair + the reply
default_tier: balanced
result: reply

tools:
  - name: list_machines
    description: >
      The catalog of commissionable machines (console-registered).
      Input: {} — returns JSON rows with name, result, budget, context keys.
  - name: run_machine
    description: >
      Commission a machine and return its outcome as JSON.
      Input: {"request": '{"target": "...", "inputs": {...}}'} — the console
      brokers HITL escalations to the human and streams live events.
  - name: ask_user
    description: >
      Ask the human one question and return the reply.
      Input: {"question": "..."}.
  - name: write_machine
    description: >
      Save an authored .mk into the workspace (filename derived from its
      machine: field) and return the validation verdict.
      Input: {"source": "<the full .mk document>"}.

context:
  user_message: ""
  history: "" # prior turns, supplied by the console session
  observation: [] # tool observations of THIS turn (accumulated)

states:
  decide: # the ReAct "think" step
    structure: >
      One line starting with exactly one of DISCOVER, RUN, CLARIFY, AUTHOR or
      REPLY, followed by the details: for RUN the machine name and the inputs
      to pass; for CLARIFY the question to ask the user; for AUTHOR the full
      requirements of the machine to create; for REPLY the substance of the
      answer.
    prompt: |
      You are the mklang console agent. You satisfy the user's request by
      commissioning machines (self-contained LLM state machines) and reporting
      results honestly. You cannot call the web yourself — only host tools
      inside a commissioned machine can (especially tool: search).

      Conversation so far: {{history}}
      User request: {{user_message}}
      Observations this turn: {{observation}}

      Choose the single next action:
      - DISCOVER — list the available machines (only if you don't already know
        a suitable one from the observations).
      - RUN — commission a machine now: name it and spell out its inputs.
        Prefer an existing machine that already does the job (stdlib or
        workspace). For live web/news research, AUTHOR or RUN a machine that
        uses the host tool `search` (see authoring rules) — never invent
        search results in generative prose.
      - CLARIFY — ask the human one precise question you cannot answer yourself.
      - AUTHOR — no existing machine covers the request: spell out the machine
        to create (purpose, inputs, states, when it should escalate). If a
        previous authoring attempt failed validation, restate the requirements
        including what to fix.
      - REPLY — the request is satisfied (or answerable directly): state the
        substance of the final answer. If a tool returned
        "no external search bound", say so clearly and how to enable search
        (TAVILY_API_KEY or MKLANG_SEARCH_BACKEND).
    tier: reasoning
    reason: true
    output: thought
    gates:
      - when: the output chooses DISCOVER
        then: ok
        to: discover
      - when: the output chooses RUN
        then: ok
        to: prepare_run
      - when: the output chooses CLARIFY
        then: ok
        to: clarify
      - when: the output chooses AUTHOR
        then: ok
        to: author
      - when: the output chooses REPLY
        then: ok
        to: reply
      - when: otherwise
        then: ok
        to: reply

  discover:
    tool: list_machines
    output: observation
    accumulate: true
    gates:
      - when: otherwise
        then: ok
        to: decide

  prepare_run: # thought → one JSON blob the run tool consumes verbatim
    structure: >
      A JSON object {"target": "<machine name>", "inputs": {<context key>:
      <value>, ...}} and nothing else. Values may be strings, numbers or lists.
    prompt: |
      Turn this decision into the run request JSON:
      {{thought}}
    tier: fast
    output: run_request
    gates:
      - when: otherwise
        then: ok
        to: do_run

  do_run: # the ReAct "act" step
    tool: run_machine
    input:
      request: "{{run_request}}"
    output: observation
    accumulate: true
    gates:
      - when: otherwise
        then: ok
        to: decide

  clarify:
    tool: ask_user
    input:
      question: "{{thought}}"
    output: observation
    accumulate: true
    gates:
      - when: otherwise
        then: ok
        to: decide

  author: # write a new machine from the decided requirements
    structure: >
      A complete, valid .mk document and nothing else — no fences, no prose
      around it.
    prompt: |
      Author the machine described here:
      {{thought}}

      Observations so far (fix any validation errors they report):
      {{observation}}

      Rules for a valid .mk document:
      - Top-level keys: mklang: "0.3", machine (snake_case name), entry,
        budget (shortest entry→END path + 2), optional default_tier / result /
        context, states. Optional top-level tools: list of {name, description}.
      - A generative state has structure (output shape), prompt (which reads
        context keys with the double-brace syntax), output (context key),
        gates. Optional: tier (fast|balanced|reasoning), reason, accumulate,
        sample: N, over (a double-brace reference to a context list),
        parse: list (output becomes a JSON-parsed list).
      - Host tools available in this console (use real `tool:` states for I/O):
        search (web — input query/max_results, returns JSON results),
        calc (arithmetic expr), search_kb, send_reply. Declare them under
        top-level tools: and call with e.g. tool: search, input mapping the
        context key that holds the query string, output notes (accumulate ok).
        NEVER put "search the web" only in a generative prompt — that fabricates
        results. For news/research: plan_query → tool search → check/finalize
        (see research_web / research_compress patterns).
      - Every gate is `when: <prose condition>` plus exactly one policy —
        `then: ok` / `repair: N` / `escalate: true` / `fail: true` — and
        `to: <state or END>` (fail has no to; escalate REQUIRES to:).
      - A state with more than one gate ends with `- when: otherwise` as the
        catch-all, last. Do not use `when: always`.
      - Declare a context default for every key the prompts read; `result`
        names a key some state outputs.
      - Never name a provider or model (route by tier).
    tier: reasoning
    output: authored_source
    gates:
      - when: otherwise
        then: ok
        to: save

  save: # persist + validate; the observation carries the check verdict
    tool: write_machine
    input:
      source: "{{authored_source}}"
    output: observation
    accumulate: true
    gates:
      - when: otherwise
        then: ok
        to: decide

  reply:
    structure: >
      The final answer for the user: plain, complete, and honest about what was
      run and what it returned (or why nothing needed to run).
    prompt: |
      User request: {{user_message}}
      Your decision: {{thought}}
      Observations this turn: {{observation}}

      Write the final reply to the user.
    output: reply
    gates:
      - when: otherwise
        then: ok
        to: END
