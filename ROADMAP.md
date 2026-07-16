# mklang — Roadmap & improvement areas

Where mklang stands (package **0.2.1**, language **0.2**) and where it can grow —
technical **and** organizational. Items are marked **[next]** (clear near-term),
**[later]** (valuable, not urgent), or **[maybe]** (worth evaluating). ADRs in
[`docs/adr/`](./docs/adr) record decisions as they're made.

## Where we are (v0.2 / package 0.2.1)

- Language core complete: states + gates + prose, tiers, `reason`, `accumulate`,
  fan-out (`sample`/`over`), sub-machine `call`, `tool` states. Cookbook patterns in
  [`SPEC.md §10`](./SPEC.md).
- JSON Schema + semantic checks; multi-provider interpreter (native Anthropic +
  OpenAI-compatible); fan-out concurrency; nested trace; CLI `run` / `check`.
- **Hardening in 0.2.1:** call-halt propagation, shared `cost_budget` under `call`,
  judge sees `reason`, judge-unparseable policy, Anthropic parity (retry /
  `ProviderError` / JSON judge / temperature), pre-run tier validation, strict
  `over` path, structured error taxonomy, cost accounting, golden + cookbook tests
  (**60** MockLLM unit tests).
- **Live:** DeepSeek e2e green (default `active: deepseek` in
  `config/runtime.example.yaml`; re-verified 2026-07-16 —
  `expense_approval.mk` → `done`). Anthropic **unit-tested**; **live e2e deferred**
  until an `ANTHROPIC_API_KEY` is available.

## Language

- **Shipped: Code-hook gates** (`hook: name`, host `(ctx, output) -> bool`, optional
  top-level `hooks:`, ADR 0006, `examples/hook_gates.mk`). Exact checks without the LLM.
- **[later] Formal types for `structure`** — optional typed I/O so composition and
  gates can be checked before spending tokens; stays opt-in over prose.
- **[maybe] Determinism knobs** — per-state seed / temperature surfaced in a
  portable way (today they live in the runtime config `params`).

## Runtime

- **Shipped (0.2.1):** see CHANGELOG — structured judge, error taxonomy, shared cost
  budget, call-failed propagation, Anthropic parity, tier validation, judge
  unparseable → `otherwise` or hard halt.
- **[later] Judge confidence score** — optional numeric confidence alongside choice.
- **[later] Async concurrency** — swap fan-out `ThreadPoolExecutor` (`max_workers=5`)
  for asyncio + bounded semaphore at large `sample`/`over` widths.
- **[later] Provider adapter registry (plugins)** — entry points for third-party
  providers.
- **[later] Caching / reproducibility** — per-state memoization for cheap replays.
- **[later] Sub-machine project manifest** — `mklang.toml` instead of loading every
  `.mk` in the folder.
- **[later] Resumable runs / checkpoints** — blackboard + position for pause/resume
  (foundation for real HITL).

## Quality

- **[next] Live-test the Anthropic adapter** — needs `ANTHROPIC_API_KEY`; unit suite
  already covers params / refusal / usage / retry / judge.
- **[later] Gated live smoke tests** — opt-in env-flagged CI runs, low token budget.

## Organizational

- **[later] Docs site** — mkdocs over `SPEC.md` + `docs/`; publish the cookbook.
- **[later] Editor tooling** — `mklang lint` beyond `check` (style, dead states).

## Integrations & extensions

- **[later] Tool plugin registry** — host tools (web search, RAG, code exec) beyond
  CLI builtins `calc` / `search`.
- **[later] Human-in-the-loop hook** — `escalate` that suspends and resumes on reply.
- **[maybe] Interop** — LangGraph export/import for invested teams.
- **[maybe] Observability export** — OpenTelemetry spans from the trace.
