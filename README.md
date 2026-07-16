# mklang

**A declarative language for LLM-driven state machines.** A `.mk` file (mk =
_machine_) describes an agent as a set of states; an LLM _is_ the runtime that
executes it. The document is the program — no host code required.

```
mklang : LangGraph  ::  a declarative spec : Python code
```

## The idea

Each **state** has four faces:

| Face        | Answers        | Example                                       |
| ----------- | -------------- | --------------------------------------------- |
| `structure` | what shape?    | "The output is an email reply, max 150 words" |
| `prompt`    | what to think? | "Write a reply to {{ticket.body}}…"           |
| `execution` | how to act?    | "Use `search_kb` at most 2 times"             |
| `gates`     | when to exit?  | see below                                     |

The output of a state is stored in the shared context under its `output:` key, so
later states read it via `{{key}}`. Four **optional** faces unlock richer reasoning:
`reason` (traced chain-of-thought), `accumulate` (append to a list), fan-out
(`sample: N` / `over: {{list}}`), and `call` (run another machine) — see
[Reasoning architectures](#reasoning-architectures).

**Gates are the transitions.** A state's `gates` list is its transition table:
each gate is a natural-language condition the LLM judges, plus what happens next.

```yaml
gates:
  - when: the reply resolves the request and is in the required tone
    then: ok
    to: send
  - when: information from the KB is missing
    repair: 2 # re-run this state with feedback, up to 2 times
    to: gather
  - when: the request needs a human
    escalate: true
    to: human_review
```

Policies: `ok` (advance), `repair(N)` (self-correct with feedback), `escalate`
(route to a handler), `fail` (abort). A global step `budget` prevents runaway loops.

## Design commitments

- **Document-first** — readable, and largely writable, by non-programmers.
- **LLM-as-runtime** — non-deterministic by design; **gates** are the safety net
  that makes it reliable.
- **Prose, not types** — `structure` and gate conditions are natural language,
  judged by the LLM at runtime. No code hooks (v0.2).
- **Provider-agnostic** — a `.mk` never names a provider or model. States route by
  capability **tier** (`fast` / `balanced` / `reasoning`); the runtime maps each
  tier to a concrete model, so the same machine runs on Anthropic, OpenAI, Google,
  or a local model unchanged.
- **Language-agnostic runtime** — the spec assumes only "some host with an LLM".

## Files

- [`SPEC.md`](./SPEC.md) — the full language specification.
- [`schema/mklang.schema.json`](./schema/mklang.schema.json) — JSON Schema that
  validates the structure of a `.mk` file (add
  `# yaml-language-server: $schema=../schema/mklang.schema.json` at the top of a
  `.mk` for editor validation).
- [`config/runtime.example.yaml`](./config/runtime.example.yaml) — host-side
  runtime config: the `tier → model` map for each provider
  ([schema](./config/runtime.schema.json)).
- [`src/mklang/`](./src/mklang) — the reference interpreter (Python, multi-provider).
- [`docs/`](./docs) — [`patterns.md`](./docs/patterns.md) (recommended configs &
  flows) and [`adr/`](./docs/adr) (design decisions); [`ROADMAP.md`](./ROADMAP.md).
- `examples/` — runnable machines:
  - [`triage.mk`](./examples/triage.mk) — branching FSM (support triage).
  - [`research.mk`](./examples/research.mk) — looping FSM (iterative Q&A).
  - [`expense_approval.mk`](./examples/expense_approval.mk) — divergent terminals + `fail`.
  - [`self_consistency.mk`](./examples/self_consistency.mk) — fan-out `sample` + reducer.
  - [`map_reduce.mk`](./examples/map_reduce.mk) + [`summarize_doc.mk`](./examples/summarize_doc.mk) — `over` + `call`.
  - [`react.mk`](./examples/react.mk) — reason/act/observe loop with `accumulate`.

## Runtime configuration

The `.mk` picks a **tier**; a host-side config picks the **model**. This is the
whole of "make it multi-provider":

```yaml
active: anthropic # anthropic | openai | google | local
providers:
  anthropic:
    tiers:
      {
        fast: claude-haiku-4-5,
        balanced: claude-sonnet-5,
        reasoning: claude-opus-4-8,
      }
  openai:
    tiers: { fast: gpt-5-mini, balanced: gpt-5, reasoning: gpt-5.4 }
  local:
    base_url: http://localhost:11434/v1
    tiers: { fast: qwen3:8b, balanced: qwen3:32b, reasoning: deepseek-r1:70b }
```

Flip `active: openai` (or `local`) and every example runs unchanged. The example
config ships blocks for **Anthropic, OpenAI, Google, DeepSeek, OpenRouter, xAI
(Grok), Mistral, and local** (Ollama/vLLM) — every non-Anthropic one is
OpenAI-compatible, so a single adapter serves them all. **OpenRouter** is a
meta-provider: its `vendor/model` ids let each tier target a different vendor
through one endpoint. Per-tier, provider-specific params (Anthropic
adaptive-thinking + `effort`, OpenAI/xAI `reasoning_effort`, …) live under
`params`. See [`config/runtime.example.yaml`](./config/runtime.example.yaml) for
the full, current-model config.

## Reasoning architectures

Every modern reasoning/agentic pattern maps onto the core (states + gates + prose +
tiers + the optional faces). Full skeletons in [`SPEC.md §10`](./SPEC.md); operating
guidance in [`docs/patterns.md`](./docs/patterns.md).

| Architecture            | mklang constructs                                                |
| ----------------------- | ---------------------------------------------------------------- |
| Chain-of-Thought        | `reason: true`                                                   |
| ReAct                   | think → `tool` state (host callable) → observation `accumulate`d |
| Reflexion / self-refine | produce → self-judge gate → `repair`                             |
| Self-consistency        | `sample: N` → reducer state (majority)                           |
| Tree-of-Thought         | `sample: k` → score/select reducer → loop (depth via budget)     |
| Plan-and-Execute        | planner (list) → `over: {{steps}}` → reducer                     |
| Debate / ensemble       | `over: {{personas}}` → synthesizer                               |
| Map-Reduce              | `over: {{chunks}}` → reducer                                     |
| Router-of-experts       | classify → `call` specialists                                    |
| Speculative cascade     | `tier: fast` draft → `escalate` → `tier: reasoning`              |

## Quickstart (reference interpreter)

```bash
cp .env.example .env            # add your provider key(s)
uv run mklang check examples/self_consistency.mk
uv run mklang run examples/self_consistency.mk \
  --provider deepseek --set question.text="What is the capital of Australia?"
```

The `.mk` picks tiers; `config/runtime.example.yaml` maps them to models; the key
comes from `.env`. Same machine, any provider.

## Status

**Language v0.2 / package 0.2.1** — core complete (fan-out, sub-machines, reasoning,
tools, context-append) with a hardened multi-provider reference interpreter.

- **Live-tested on DeepSeek**; Anthropic adapter is unit-tested (live e2e when a key
  is available). The spec stays language- and provider-agnostic. See
  [`ROADMAP.md`](./ROADMAP.md) for what's next and [`CHANGELOG.md`](./CHANGELOG.md)
  for the history.

## License

[Apache-2.0](./LICENSE). Contributions welcome — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).
