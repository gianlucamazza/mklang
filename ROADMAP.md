# mklang — Roadmap & improvement areas

Where mklang stands (package **0.4.0**, language **0.2**) and where it can grow —
technical **and** organizational. Items are marked **[next]** (clear near-term),
**[later]** (valuable, not urgent), or **[maybe]** (worth evaluating). ADRs in
[`docs/adr/`](./docs/adr) record decisions as they're made.

## Where we are (v0.2 / package 0.4.0)

- Language core complete: states + gates + prose, tiers, `reason`, `accumulate`,
  fan-out (`sample`/`over`), sub-machine `call`, `tool` states, **code-hook gates**.
  Cookbook in [`SPEC.md §10`](./SPEC.md).
- JSON Schema + semantic checks; multi-provider interpreter; nested trace; CLI.
- **0.2.1 hardening:** call-halt, shared cost budget, judge reasoning, judge-unparseable,
  Anthropic parity, tier validation, strict `over`, error taxonomy (~70 MockLLM tests).
- **0.2.2:** code-hook gates (ADR 0006); tool/hook **entry-point plugins**; default
  `active: deepseek` with live smoke re-verified.
- **0.3.0:** **resumable runs / checkpoints** (ADR 0007) — budget exhaustion suspends
  into a JSON checkpoint (`--checkpoint`), `mklang resume` continues as if
  uninterrupted; foundation for HITL.
- **0.4.0:** **human-in-the-loop** (ADR 0008) — `--hitl` makes fired `escalate`
  gates suspend; `mklang resume --set human.reply=…` injects the decision.
- **Live:** DeepSeek e2e green. Anthropic unit-tested; live e2e deferred without key.

## Language

- **Shipped:** code-hook gates (`hook:`, `hooks:`, host bool predicates).
- **[later] Formal types for `structure`** — optional typed I/O before spending tokens.
- **[maybe] Determinism knobs** — portable seed / temperature in the `.mk`.

## Runtime

- **Shipped:** structured judge, error taxonomy, shared cost budget, call-failed,
  Anthropic parity, tier validation, tool/hook plugin registries via entry points.
- **[later] Judge confidence score** — numeric confidence alongside choice.
- **[later] Async concurrency** — asyncio fan-out beyond `ThreadPoolExecutor(5)`.
- **[later] Provider adapter registry (plugins)** — entry points for LLM providers
  (tools/hooks already use entry points).
- **[later] Caching / reproducibility** — per-state memoization.
- **[later] Sub-machine project manifest** — `mklang.toml`.
- **Shipped (0.3.0):** resumable runs / checkpoints — blackboard + position
  pause/resume on budget exhaustion (ADR 0007), foundation for real HITL.

## Quality

- **Shipped:** gated live smoke tests — provider-agnostic, opt-in via
  `MKLANG_LIVE=1` (`MKLANG_LIVE_PROVIDER=<name>` to override the config's
  `active`); skips cleanly when the key is missing. Anthropic goes through the
  same path as every other provider.
- **[next] Anthropic live pass** — blocked only on a key: set `ANTHROPIC_API_KEY`
  and run `MKLANG_LIVE=1 MKLANG_LIVE_PROVIDER=anthropic pytest tests/test_live.py`.

## Organizational

- **[later] Docs site** — mkdocs over SPEC + docs.
- **[later] Editor tooling** — `mklang lint` beyond `check`.

## Integrations & extensions

- **Shipped:** tool plugin registry (`mklang.tools` entry points) and hook plugins
  (`mklang.hooks`); builtins remain available offline.
- **Shipped (0.4.0):** human-in-the-loop — `escalate` suspends (`--hitl`) and
  resumes on reply (`resume --set`), ADR 0008. A per-gate `hitl:` field is the
  natural [maybe] extension if run-level opt-in proves too coarse.
- **[maybe] Interop** — LangGraph export/import.
- **[maybe] Observability export** — OpenTelemetry spans from the trace.
