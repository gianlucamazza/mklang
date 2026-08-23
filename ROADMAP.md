# mklang — Roadmap & improvement areas

Where mklang stands (package **1.3.1**, language **0.4**) and where it can grow —
technical **and** organizational.

**Tracking rule:** every **Now** / **Next** bullet has a GitHub issue. Work lives
in [issues](https://github.com/gianlucamazza/mklang/issues) +
[project board](https://github.com/users/gianlucamazza/projects/2); this file is
the strategic index. ADRs in [`docs/adr/`](./docs/adr) record decisions.
Milestone **[1.1 — maturity & embed docs](https://github.com/gianlucamazza/mklang/milestone/1)**
is the active package horizon (spec at **0.4** since 1.2.0).

Horizon tags below: **[now]** / **[next]** / **[later]** / **[maybe]**.

---

## Now

Active focus (milestone 1.1, `horizon:now`):

- **[now] Live-verify Anthropic** (three-provider gate-divergence) — [#60](https://github.com/gianlucamazza/mklang/issues/60)
- **[now] Five-reader distribution test (D1)** — [#61](https://github.com/gianlucamazza/mklang/issues/61)

## Next

Doc/schema + release-floor items **shipped** in [#73](https://github.com/gianlucamazza/mklang/pull/73)
([#64](https://github.com/gianlucamazza/mklang/issues/64), [#69](https://github.com/gianlucamazza/mklang/issues/69)–[#72](https://github.com/gianlucamazza/mklang/issues/72) closed). Remaining Now items need live ops or humans:

- **[next]** Third-provider (Anthropic) gate-divergence pass: close [#60](https://github.com/gianlucamazza/mklang/issues/60) and re-check release floors
- **[next]** Five-reader distribution test — [#61](https://github.com/gianlucamazza/mklang/issues/61)

### Evidence backlog

The dated experiment logs live in the repo, not on the docs site:

- **Gate divergence** ([protocol + results](./docs/experiments/gate-divergence.md)) —
  first live rows landed 2026-08-09; a third provider is [#60](https://github.com/gianlucamazza/mklang/issues/60).
- **Repair convergence** ([protocol + results](./docs/experiments/repair-convergence.md)) —
  first measured row landed 2026-08-20 (`lift` −0.41 on DeepSeek, 13 second attempts);
  a second provider is what ADR 0031 §3 still needs.
- **Control-flow-taint incidence** ([protocol](./docs/experiments/taint-incidence.md)) —
  harness exists (`scripts/taint_incidence.py`); the external-machine corpus waits on
  distribution ([#61](https://github.com/gianlucamazza/mklang/issues/61)).

## Later

Valuable, not in 1.1 (open issues only when ready to pull into a milestone):

- **[later] Truncation `continue` stitching** (ADR 0018)
- **[later] Editor tooling / LSP**
- **[later] Language 0.4 candidates** (each needs ADR + conformance — see BP §16):
  portable `on_truncate`, per-gate `hitl:`, budget split. Shipped from this list in
  0.4: `max_visits` (ADR 0033), `parse: json` (ADR 0034), escalate `ask:`/`reply_to:`
  (ADR 0035)
- **[later] Host HTTP tool as documented plugin** (not core language)
- **[later] Context Layer 2 zones/pin** (ADR 0017; provenance taint already ADR 0025)

## Maybe

Worth evaluating; not committed:

- **[maybe]** Async fan-out beyond `ThreadPoolExecutor(5)`; per-state caching
- **[maybe]** External console client (MCP-only); LangGraph interop
- **[maybe]** OpenTelemetry export from the run trace
- **[maybe]** Separate host package (webhook + scheduler) — product host, not language core
- **[maybe]** FS multi-root / path rules (ADR 0024 defer)

## Non-goals

Permanent or deferred-out of the stable language surface — see
[SPEC §9](./SPEC.md) and [stability guide](./docs/guides/stability.md):
formal types in `structure`, provider/model pinning in `.mkl`, dual-channel
CaMeL control planes (research).

---

## Language

- **Shipped:** code-hook gates (`hook:`, `hooks:`, host bool predicates).
- **Shipped:** untrusted-context delimiting — provenance taint + `<data-NONCE>`
  fences in produce and judge prompts (SPEC §6,
  [ADR 0025](./docs/adr/0025-untrusted-context-delimiting.md)). Follow-up
  audit closed: the console brain is covered via `engine.run` (fence
  regression test), `llmlint` probes use author faces only, and `resolve()`
  tool/call inputs stay raw by design. Dual-channel / CaMeL-style control
  stays open (§9).
- **[later] Formal types for `structure`** — optional typed I/O before spending tokens.
- **[maybe] Determinism knobs** — portable seed / temperature in the `.mkl`.

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

- **Shipped:** CI quality gates — mypy (zero suppressions, every function in
  `src/mklang` annotated) with an **add-only strict tier** for eleven leaf
  modules (full `--strict` minus `disallow_any_generics`, the documented JSON
  idiom — modules may only ever be added to the tier, the inverse of a
  relaxation list); pytest-cov with a `fail_under = 90` coverage gate (92%
  measured; ratchet up, never down); and an offline test matrix (ubuntu
  3.11–3.13 + macOS + Windows) in a reusable `quality.yml` workflow shared by
  `ci.yml` and `release.yml` (pinned to the release tag).
- **Shipped:** gated live smoke tests — provider-agnostic, opt-in via
  `MKLANG_LIVE=1` (`MKLANG_LIVE_PROVIDER=<name>` to override the config's
  `active`); skips cleanly when the key is missing. Anthropic goes through the
  same path as every other provider.
- **Shipped:** cross-provider **gate-divergence** harness —
  [`scripts/gate_divergence.py`](./scripts/gate_divergence.py) +
  [`docs/experiments/gate-divergence.md`](./docs/experiments/gate-divergence.md)
  — now a **four-machine suite**, each stressing a different gate shape
  (multi-way `ok` routing, borderline judgement, control-flow `escalate`,
  `repair` grounding). `--machines` selects the set (default the single
  `gate_divergence` for release-gate comparability, or `all`); agreement and
  the `--min-agreement` release floor are computed **per-machine** (cross-machine
  signatures differ by construction). The harness is offline-testable via an
  injectable `build_llm`. Document portability stays syntactic until agreement
  is measured live at scale.
- **Shipped (results, 2026-07-16):** first gate-divergence table —
  deepseek×openai, 3 repeats each, **agreement rate 1.0** on the single spam
  machine (tier-following judges). Dated row in
  [`docs/experiments/gate-divergence.md`](./docs/experiments/gate-divergence.md).
  A third-provider (Anthropic) pass is tracked as [#60](https://github.com/gianlucamazza/mklang/issues/60).
- **Shipped:** LLM-assisted lint (`mklang lint --llm`,
  [ADR 0010](./docs/adr/0010-llm-assisted-lint.md), Accepted) — opt-in probe of
  ambiguous / overlapping prose `when` conditions with the real gate judge
  (K synthetic outputs × R judge repeats per multi-gate state). Advisory only:
  never a `--strict` error source, never in the offline CI path.
- **Shipped (multi-provider live, 0.14.0 & 0.15.0 release matrices):** DeepSeek +
  **OpenAI** live smoke and gate agreement green through both release pipelines.
  **Anthropic** adapter remains unit-tested; the live third-provider pass is
  [#60](https://github.com/gianlucamazza/mklang/issues/60).

## Integrations & extensions

- **Shipped — web search host tool** ([ADR 0016](./docs/adr/0016-host-web-search-tool.md)
  Accepted) — structured `search` stub default; fake/tavily backends;
  optional `days`/`topic`/`published_date`; `research_web.mkl` + scenario tests;
  host `context.today` convention for time-sensitive machines; `std_research`
  shipped in 0.12.0; `runtime.yaml` `tools:` block shipped (env > config >
  default, doctor reports the deciding source).
- **Shipped — host tool stub architecture** ([ADR 0020](./docs/adr/0020-host-tool-stub-architecture.md))
  — uniform JSON envelope for I/O tools; `search_kb` / `send_reply` stub+fake
  backends; honest default `send_reply` (`sent: false`).
- **Shipped — context rendering Layer 0–1** ([ADR 0017](./docs/adr/0017-context-content-management.md)
  Accepted) — judge CONTEXT marker; produce-prompt value cap; console
  `history_for_brain`; compress pattern (`research_compress.mkl`). **[later]**
  language faces / `std_compress`.
- **Shipped — output anti-cutoff** ([ADR 0018](./docs/adr/0018-output-truncation-anti-cutoff.md)
  Accepted) — detect/trace/events; `report`/`halt` on CLI · MCP · console ·
  scripttest; adapter fixtures. **[later]** `continue` stitching.
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
  ten bundled general-purpose `std_*` architecture machines (CoT,
  self-consistency, refine, ToT, debate, map-reduce, cascade, plan-execute,
  research, compress), present in every
  registry with user-wins precedence, runnable by name from CLI/MCP, extensible
  via the `mklang.machines` entry-point group. Catalog: `docs/reference/stdlib.md`.
- **Shipped (0.3):** structured list outputs — `parse: list` deposits a parsed
  JSON array and whole-template `input:` values pass raw across `call:`/`tool:`
  ([ADR 0014](./docs/adr/0014-structured-list-outputs.md)); Plan-and-Execute
  ships as `std_plan_execute`.
- **Shipped (M1–M3):** console surface (`mklang console`,
  [ADR 0015](./docs/adr/0015-console-surface.md), [docs/guides/console.md](./docs/guides/console.md))
  — agent-first Textual TUI; authoring loop; sessions/`--continue`; activity
  tree + inspector; slash commands + `/resume`; brain history windowed for
  prompts (ADR 0017).
- **Shipped (package polish):** console **conversation rendering** — agent
  replies as CommonMark; slash/JSON/YAML fenced; user text and activity-tree
  labels/previews as plain styled `Text` (no Rich-markup injection of untrusted
  content). Docs: [console](./docs/guides/console.md#conversation-rendering),
  [best practices](./docs/guides/best-practices.md) anti-pattern #12.
- **Shipped:** live engine events on the MCP transport
  ([ADR 0019](./docs/adr/0019-mcp-live-events.md)) — `run`/`resume` stream the
  `on_event` sequence as `mklang.event` logging notifications; any MCP client
  can render run progress without touching the engine.
- **[maybe] External console client** — an OpenTUI/Ink-class front-end as a
  separate project speaking MCP; needs nothing new server-side (ADR 0019).
- **[maybe] Interop** — LangGraph export/import.
- **[maybe] Observability export** — OpenTelemetry spans from the trace
  (projection of the run trace; process logging stays host-side — see
  [best practices §12](./docs/guides/best-practices.md)).
- **[shipped] Process logging hygiene** — `mklang.*` `logging` hierarchy on
  stderr, `MKLANG_LOG_LEVEL` / `--log-level` (CLI and `mklang-mcp`); never
  replaces trace/events (BP §12).
- **[shipped] FS data tools (ADR 0024)** — class-3 `list_files`/`read_file`/
  `write_file` builtins with a coding-tool workspace model: live reads confined
  to `--workspace`/`MKLANG_FS_ROOT`/cwd, grant-gated writes; not console brain
  defaults; not language faces (BP §13).
- **[maybe] FS multi-root and path rules** — `--add-dir`/`writable_roots`
  analog and per-path allow/deny rules (`Read(...)`/`Edit(...)` syntax shared
  by Claude Code and Grok); ADR 0024 defers both until a real use case appears.
