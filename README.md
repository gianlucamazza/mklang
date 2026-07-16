# mklang

[![CI](https://github.com/gianlucamazza/mklang/actions/workflows/ci.yml/badge.svg)](https://github.com/gianlucamazza/mklang/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-gianlucamazza.github.io%2Fmklang-blue)](https://gianlucamazza.github.io/mklang/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](./LICENSE)

**A declarative language for LLM-driven state machines.** A `.mk` file (mk =
_machine_) describes an agent as a set of states; an LLM _is_ the runtime that
executes generative steps. The document is the program; the host supplies the
interpreter, optional tools, and optional code-hook gates.

```
mklang : LangGraph  ::  a declarative spec : Python code
```

## The idea

Each **state** has four faces:

| Face        | Answers        | Example                                       |
| ----------- | -------------- | --------------------------------------------- |
| `structure` | what shape?    | "The output is an email reply, max 150 words" |
| `prompt`    | what to think? | "Write a reply to {{ticket.body}}…"           |
| `execution` | how to act?    | "Do not invent policies not in the KB facts"  |
| `gates`     | when to exit?  | see below                                     |

Real side effects (search, send, calc) are **`tool:` states** — host callables,
not prose in `execution`. See [`examples/react.mk`](./examples/react.mk) and
[`examples/triage.mk`](./examples/triage.mk).

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

- **Document-first** — readable without the interpreter; prose-first for the
  common path. Production machines still need developer judgment for tools,
  hooks, and untrusted inputs (see SPEC threat model).
- **LLM-as-runtime** — non-deterministic by design; **gates** (prose + optional
  code hooks + budgets + trace) are the reliability mechanism. Prose-gate accuracy
  is an empirical claim, not a free lunch.
- **Prose, not types** — `structure` and gate conditions are natural language,
  judged by the LLM at runtime; optional `hook:` gates add host bool checks.
- **Provider-agnostic** — a `.mk` never names a provider or model. States route by
  capability **tier** (`fast` / `balanced` / `reasoning`); the runtime maps each
  tier to a concrete model. Portability of the document is syntactic; whether
  different providers fire the same gates on the same run is measurable (see
  `scripts/gate_divergence.py`).
- **Spec + conformance** — an implementation-neutral [conformance suite](./conformance/README.md)
  pins interpreter semantics so a second runtime can match the language contract.
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
  - [`triage.mk`](./examples/triage.mk) — branching FSM + real `search_kb` / `send_reply` tools.
  - [`research.mk`](./examples/research.mk) — looping FSM (iterative Q&A).
  - [`expense_approval.mk`](./examples/expense_approval.mk) — divergent terminals + `fail`.
  - [`self_consistency.mk`](./examples/self_consistency.mk) — fan-out `sample` + reducer.
  - [`map_reduce.mk`](./examples/map_reduce.mk) + [`summarize_doc.mk`](./examples/summarize_doc.mk) — `over` + `call`.
  - [`react.mk`](./examples/react.mk) — reason/act/observe loop with `accumulate`.
  - [`hook_gates.mk`](./examples/hook_gates.mk) — deterministic code-hook gates (exact policy).

## Runtime configuration

The `.mk` picks a **tier**; a host-side config picks the **model**. This is the
whole of "make it multi-provider":

```yaml
active: deepseek # deepseek | anthropic | openai | google | openrouter | xai | mistral | local
providers:
  deepseek:
    base_url: https://api.deepseek.com
    tiers:
      {
        fast: deepseek-chat,
        balanced: deepseek-chat,
        reasoning: deepseek-reasoner,
      }
  anthropic:
    tiers:
      {
        fast: claude-haiku-4-5,
        balanced: claude-sonnet-5,
        reasoning: claude-opus-4-8,
      }
  local:
    base_url: http://localhost:11434/v1
    tiers: { fast: qwen3:8b, balanced: qwen3:32b, reasoning: deepseek-r1:70b }
```

The example config defaults to **DeepSeek** (the path we live-test against). Flip
`active: anthropic` (or `openai` / `local` / …) and every example runs unchanged.
Blocks ship for **Anthropic, OpenAI, Google, DeepSeek, OpenRouter, xAI (Grok),
Mistral, and local** (Ollama/vLLM) — every non-Anthropic one is OpenAI-compatible,
so a single adapter serves them all. **OpenRouter** is a meta-provider: its
`vendor/model` ids let each tier target a different vendor through one endpoint.
Per-tier params (Anthropic adaptive-thinking + `effort`, OpenAI/xAI
`reasoning_effort`, …) live under `params`. Full map:
[`config/runtime.example.yaml`](./config/runtime.example.yaml).

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
| Exact policy checks     | gate `hook:` host `(ctx, output) -> bool` (no LLM)               |

## Install

```bash
pip install git+https://github.com/gianlucamazza/mklang   # PyPI release coming
```

Editor validation for `.mk` files works out of the box via the JSON Schema —
point yaml-language-server at
`https://raw.githubusercontent.com/gianlucamazza/mklang/main/schema/mklang.schema.json`.

## Quickstart (reference interpreter)

```bash
cp .env.example .env            # set DEEPSEEK_API_KEY=… (or another provider key)
uv run mklang check examples/self_consistency.mk
uv run mklang lint examples/self_consistency.mk   # + static analysis
uv run mklang run examples/self_consistency.mk \
  --set question.text="What is the capital of Australia?"
# default provider is deepseek; override with --provider anthropic|openai|…

# pause on budget, resume later (exit code 3 = suspended):
uv run mklang run examples/self_consistency.mk --max-tokens 300 --checkpoint ck.json
uv run mklang resume ck.json --max-tokens 5000

# human-in-the-loop: escalate gates suspend; resume with the human decision:
uv run mklang run examples/expense_approval.mk --checkpoint ck.json --hitl
uv run mklang resume ck.json --set human.reply="approved, cost center 42"
```

The `.mk` picks tiers; `config/runtime.example.yaml` maps them to models (`active:
deepseek` by default); the key comes from `.env`. Same machine, any provider.

## Test your machine without API keys

`mklang test` runs your machine against a script of named scenarios with a
**scripted LLM** (produce texts, judge picks) and scripted tools/hooks — fully
deterministic, no provider or key. It pins the paths you care about *before* you
spend a token on a live run.

```bash
uv run mklang test examples/triage.mk --script examples/triage.test.yaml
# PASS happy-path
# PASS kb-empty-escalates
```

Each scenario declares a scripted `llm:`/`tools:`/`hooks:` and an `expect:`
(status, error, result, `at`, `trace` skeleton, context keys) — the same case
format the [conformance suite](./conformance/README.md) uses. A mismatch prints a
minimal diff (the first differing key, expected vs actual) and exits 1. See
[`examples/triage.test.yaml`](./examples/triage.test.yaml).

## Status

**Language v0.2 / package 0.5.3** — core complete: states + gates + prose, tiers,
`reason` / `accumulate` / fan-out / `call` / `tool` states / code-hook gates;
multi-provider interpreter with entry-point plugins (tools, hooks, providers);
resumable checkpoints (`mklang resume`, ADR 0007); human-in-the-loop (`--hitl`,
ADR 0008); `mklang check` / `lint` / **`test`** (scripted scenarios, no API keys);
implementation-neutral **[conformance suite](./conformance/README.md)** (ADR 0009).
Gate judging follows the state tier by default; see CHANGELOG 0.5.2 for the
observable change and 0.5.3 for authoring tooling.

- **Live-tested on DeepSeek** (default `active` provider; re-verified 2026-07-16 on
  `examples/expense_approval.mk`). Anthropic is unit-tested; live e2e needs
  `ANTHROPIC_API_KEY`. PyPI publish and cross-provider gate-divergence results are
  the main open items.
- Roadmap and full release notes: [`ROADMAP.md`](./ROADMAP.md),
  [`CHANGELOG.md`](./CHANGELOG.md).

## License

[Apache-2.0](./LICENSE). Contributions welcome — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).
