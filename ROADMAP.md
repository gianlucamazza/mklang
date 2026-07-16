# mklang — Roadmap & improvement areas

Where mklang stands (v0.2) and where it can grow — technical **and** organizational.
Items are marked **[next]** (clear near-term), **[later]** (valuable, not urgent), or
**[maybe]** (worth evaluating). This is a living document; ADRs in
[`docs/adr/`](./docs/adr) record decisions as they're made.

## Where we are (v0.2)

- Language core complete: states + gates + prose, tiers, `reason`, `accumulate`,
  fan-out (`sample`/`over`), sub-machine `call`. Every reasoning architecture in the
  cookbook maps onto it ([`SPEC.md §10`](./SPEC.md)).
- JSON Schema (`oneOf` generative|call) validates structure; semantic checks in the
  loader (reachability, unknown targets, unresolved `call`, catch-all warnings).
- Reference interpreter (`src/mklang/`): multi-provider (native Anthropic +
  OpenAI-compatible for DeepSeek/OpenAI/OpenRouter/xAI/Mistral/local), fan-out
  concurrency, nested trace, CLI (`run`/`check`). Deterministic tests on a MockLLM;
  **live-tested on DeepSeek**.
- Hardening pass (v0.2.x): per-tier `params` now **applied** to the model
  (effort/thinking/reasoning_effort, best-effort with drop-on-error); pre-run
  validation in `mklang run`; engine exception-safety (clean `halt`, isolated
  fan-out branches); schema bundled for pip-install; `.env` from cwd; `mklang: "0.2"`
  version field; transient-error retry; dead-state / unproduced-`result` checks.
- Milestone 6: **`tool` states** (real ReAct — host callables, observations re-enter
  the context); structured-output judge; error taxonomy (`refusal`/`provider-error`);
  token/cost accounting + cost budget; Apache-2.0 + CONTRIBUTING + CHANGELOG;
  golden-trace + cookbook-conformance tests; Anthropic adapter unit-tested.

## Language

- **[later] Code-hook gates** — a gate evaluated by a host function returning a bool,
  for exact/critical checks (`total == sum(lines)`), alongside LLM-judged gates.
- **[later] Formal types for `structure`** — optional typed I/O so composition and
  gates can be checked before spending tokens; stays opt-in over prose.
- **[maybe] Determinism knobs** — per-state seed / temperature surfaced in a
  portable way (today they live in the runtime config `params`).

## Runtime

- **Shipped (see CHANGELOG):** structured-output judge (OpenAI-compat + Anthropic JSON
  / regex fallback via shared `parse_choice`), error taxonomy (`refusal` /
  `provider-error` / `call-failed` / `cost-exhausted`), token/cost accounting +
  `cost_budget`, `reason` passed to the judge (SPEC §4.5), sub-machine halt
  propagation (`call-failed`), Anthropic parity (retry, `ProviderError`, temperature
  without thinking), pre-run tier validation in `mklang run`.
- **[later] Judge confidence / hard-fail on unparseable** — optional halt instead of
  soft-fallback to the last (`otherwise`) gate when the judge returns garbage.
- **[later] Async concurrency** — swap the fan-out `ThreadPoolExecutor` for asyncio
  with a bounded semaphore; matters at large `sample`/`over` widths. Document the
  current `max_workers=5` limit until then.
- **[later] Provider adapter registry (plugins)** — register adapters via entry
  points so third parties add providers without touching core.
- **[later] Caching / reproducibility** — per-state memoization (same input+prompt →
  same output) for cheap deterministic replays and cost savings.
- **[later] Sub-machine project manifest** — an `mklang.toml` naming the machine
  directory and entry, instead of "load every `.mk` in the folder".
- **[later] Resumable runs / checkpoints** — persist the blackboard + position so a
  long agentic run can pause and resume (needed for human-in-the-loop escalation).

## Quality

- **[next] Live-test the Anthropic adapter** — the adapter is unit-tested (params /
  refusal / usage), but no `ANTHROPIC_API_KEY` was available for an end-to-end run.
- **[later] Gated live smoke tests** — opt-in (env-flagged) runs against a real
  provider in CI, low token budget.

## Organizational

- **[later] Docs site** — mkdocs over `SPEC.md` + `docs/`; publish the cookbook.
- **[later] Editor tooling** — the `yaml-language-server` schema hint already gives
  completion/validation; add a `mklang lint` beyond `check` (style, dead states).

## Integrations & extensions

- **[later] Tool plugin registry** — host-provided tools (web search, RAG, code
  exec) surfaced to `execution`, paired with the formal `tools:` block.
- **[later] Human-in-the-loop hook** — an `escalate` target that suspends the run and
  emits a request to an external system, resuming on reply.
- **[maybe] Interop** — export a deterministic subset to LangGraph, or import from
  it, for teams already invested there.
- **[maybe] Observability export** — OpenTelemetry spans from the trace for existing
  dashboards.
