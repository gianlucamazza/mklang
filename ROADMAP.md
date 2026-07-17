# mklang — Roadmap & improvement areas

Where mklang stands (package **0.6.0**, language **0.3**) and where it can grow —
technical **and** organizational. Items are marked **[next]** (clear near-term),
**[later]** (valuable, not urgent), or **[maybe]** (worth evaluating). ADRs in
[`docs/adr/`](./docs/adr) record decisions as they're made.

## Where we are (v0.2 / package 0.5.4)

- Language core complete: states + gates + prose, tiers, `reason`, `accumulate`,
  fan-out (`sample`/`over`), sub-machine `call`, `tool` states, **code-hook gates**.
  Cookbook in [`SPEC.md §10`](./SPEC.md).
- JSON Schema + semantic checks; multi-provider interpreter; nested trace; CLI.
- **0.2.1 hardening:** call-halt, shared cost budget, judge reasoning, judge-unparseable,
  Anthropic parity, tier validation, strict `over`, error taxonomy (MockLLM unit suite;
  full offline coverage today is unit + conformance + `mklang test` — see pytest).
- **0.2.2:** code-hook gates (ADR 0006); tool/hook **entry-point plugins**; default
  `active: deepseek` with live smoke re-verified.
- **0.3.0:** **resumable runs / checkpoints** (ADR 0007) — budget exhaustion suspends
  into a JSON checkpoint (`--checkpoint`), `mklang resume` continues as if
  uninterrupted; foundation for HITL.
- **0.4.0:** **human-in-the-loop** (ADR 0008) — `--hitl` makes fired `escalate`
  gates suspend; `mklang resume --set human.reply=…` injects the decision.
- **0.5.0:** **language-grade rigor** — conformance suite (ADR 0009),
  `mklang lint`, provider entry-point plugins, CI + docs site, public packaging.
- **0.5.1:** showcase honesty (`triage.mk` real tool states), silent judge-clamp
  fix, normative judge protocol, threat model (§11), gate-divergence scaffold.
- **0.5.2 (second remediation pass):** gate judging **follows the state tier** by
  default (§2.1; `judge:` becomes an opt-in override) — an observable-behavior
  change; strict judge-reply parsing (`bare`/`last-number`, traced `judge_parse`);
  `{{index}}` in `sample` branches; `unresolved-interpolation` lint; `--strict`
  rejects unsupported `mklang:` versions; `0600` checkpoints + §11 at-rest note;
  conformance now covers hook precedence and `tool` states.
- **0.5.3 (third remediation pass):** **`mklang test`** — deterministic scenario
  testing with a scripted LLM, no API keys, sharing one matcher module
  (`scripttest.py`) with the conformance runner; static budget-feasibility check
  (`budget-infeasible`); dotted-segment lint on inline context maps (completes F7);
  schema-copy identity test; ADR 0010 (LLM-assisted lint, Proposed).
- **0.5.4 (release readiness):** reproducible GitHub Release → PyPI Trusted
  Publishing; clean-wheel smoke; DeepSeek + OpenAI blocking live matrix; optional
  provider report; enforceable gate-divergence thresholds.
- **Live (2026-07-16):** DeepSeek + OpenAI smoke green. Anthropic unit-tested;
  live blocked by account billing (key exists). Gate-divergence deepseek×openai
  agreement **1.0** (3× each) on the synthetic harness.

## Language

- **Shipped:** code-hook gates (`hook:`, `hooks:`, host bool predicates).
- **[later] Formal types for `structure`** — optional typed I/O before spending tokens.
- **[maybe] Determinism knobs** — portable seed / temperature in the `.mk`.

## Runtime

- **Shipped:** structured judge, error taxonomy, shared cost budget, call-failed,
  Anthropic parity, tier validation, tool/hook plugin registries via entry points.
- **[later] Judge confidence score** — numeric confidence alongside choice.
- **[maybe] Budget split** — a fan-out charges `max(1, len(branches))` steps, so the
  single `budget:` couples the loop guard with a fan-out volume cap (SPEC §7). A v0.3
  ADR could split it into a transition `budget` and a separate `branch_budget` for
  fan-out width; decide via ADR, keep one number in v0.2.
- **[later] Async concurrency** — asyncio fan-out beyond `ThreadPoolExecutor(5)`.
- **Shipped (0.5.0):** provider adapter registry — `mklang.providers` entry
  points; OpenAI-compatible stays the default for unregistered names.
- **[later] Caching / reproducibility** — per-state memoization.
- **[later] Sub-machine project manifest** — `mklang.toml`.
- **Shipped (0.3.0):** resumable runs / checkpoints — blackboard + position
  pause/resume on budget exhaustion (ADR 0007), foundation for real HITL.

## Quality

- **Shipped:** gated live smoke tests — provider-agnostic, opt-in via
  `MKLANG_LIVE=1` (`MKLANG_LIVE_PROVIDER=<name>` to override the config's
  `active`); skips cleanly when the key is missing. Anthropic goes through the
  same path as every other provider.
- **Shipped (scaffold):** cross-provider **gate-divergence** harness —
  [`scripts/gate_divergence.py`](./scripts/gate_divergence.py) +
  [`docs/experiments/gate-divergence.md`](./docs/experiments/gate-divergence.md).
  Document portability is syntactic until agreement rates are measured live.
- **Shipped (results, 2026-07-16):** first gate-divergence table —
  deepseek×openai, 3 repeats each, **agreement rate 1.0** on the synthetic spam
  machine (tier-following judges). Dated row in
  [`docs/experiments/gate-divergence.md`](./docs/experiments/gate-divergence.md).
  Re-run when model IDs or judge defaults change; Anthropic still billing-blocked.
- **Shipped:** LLM-assisted lint (`mklang lint --llm`,
  [ADR 0010](./docs/adr/0010-llm-assisted-lint.md), Accepted) — opt-in probe of
  ambiguous / overlapping prose `when` conditions with the real gate judge
  (K synthetic outputs × R judge repeats per multi-gate state). Advisory only:
  never a `--strict` error source, never in the offline CI path.
- **Shipped (partial multi-provider live, 2026-07-16):** DeepSeek + **OpenAI**
  live smoke green (`MKLANG_LIVE=1 MKLANG_LIVE_PROVIDER=…`). **Anthropic** adapter
  remains unit-tested; live e2e blocked by **account billing/credits**, not by a
  missing key (key present in 1Password; API returns purchase-credits error).

## Organizational

- **Shipped (0.5.0):** docs site (mkdocs-material on GitHub Pages, assembled
  from the repo's canonical markdown) and `mklang lint` (static analysis
  beyond `check`); conformance suite as the language contract (ADR 0009).
- **0.5.4 release path:** a published GitHub Release builds and tests one artifact
  set, requires DeepSeek + OpenAI live agreement, then publishes through PyPI
  Trusted Publishing (OIDC, no long-lived package token). The one-time external
  setup is the `mklang` pending publisher plus the protected GitHub `pypi`
  environment and provider secrets.
- **[later] Editor tooling** — LSP / syntax highlighting beyond the YAML
  schema; `mklang lint` is the first brick.
- **[maybe] Rename `.mk` extension** — collides with Makefile includes /
  GitHub Linguist; cost of rename is low today, high after adoption (SPEC §9).

## Integrations & extensions

- **Shipped:** tool plugin registry (`mklang.tools` entry points) and hook plugins
  (`mklang.hooks`); builtins remain available offline.
- **Shipped (0.4.0):** human-in-the-loop — `escalate` suspends (`--hitl`) and
  resumes on reply (`resume --set`), ADR 0008. A per-gate `hitl:` field is the
  natural [maybe] extension if run-level opt-in proves too coarse.
- **Shipped:** MCP server surface (`mklang-mcp`, extra `mklang[mcp]`,
  [ADR 0011](./docs/adr/0011-mcp-server-surface.md)) — optional stdio MCP host so
  agentic clients can commission a machine (`run`/`resume`, inline source or path)
  and get `trace` + `usage` back, without embedding the library. Suspended runs
  hold their frames in an in-memory session store behind opaque single-use
  handles; the core install stays offline with no `mcp` present.
- **Shipped:** machine stdlib ([ADR 0012](./docs/adr/0012-machine-stdlib.md)) —
  eight bundled general-purpose `std_*` architecture machines (CoT,
  self-consistency, refine, ToT, debate, map-reduce, cascade, plan-execute), present in every
  registry with user-wins precedence, runnable by name from CLI/MCP, extensible
  via the `mklang.machines` entry-point group. Catalog: `docs/stdlib.md`.
- **Shipped (0.3):** structured list outputs — `parse: list` deposits a parsed
  JSON array and whole-template `input:` values pass raw across `call:`/`tool:`
  ([ADR 0014](./docs/adr/0014-structured-list-outputs.md)); Plan-and-Execute
  ships as `std_plan_execute`.
- **[maybe] Interop** — LangGraph export/import.
- **[maybe] Observability export** — OpenTelemetry spans from the trace.
