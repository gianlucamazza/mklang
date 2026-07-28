# mklang — Roadmap & improvement areas

Where mklang stands (package **1.1.1**, language **0.3**) and where it can grow —
technical **and** organizational.

**Tracking rule:** every **Now** / **Next** bullet has a GitHub issue. Work lives
in [issues](https://github.com/gianlucamazza/mklang/issues) +
[project board](https://github.com/users/gianlucamazza/projects/2); this file is
the strategic index. ADRs in [`docs/adr/`](./docs/adr) record decisions.
Milestone **[1.1 — maturity & embed docs](https://github.com/gianlucamazza/mklang/milestone/1)**
is the active package horizon (spec stays **0.3**).

Horizon tags below: **[now]** / **[next]** / **[later]** / **[maybe]**.

---

## Now

Active focus (milestone 1.1, `horizon:now`):

- **[now] Live-verify Anthropic** (three-provider gate-divergence) — [#60](https://github.com/gianlucamazza/mklang/issues/60)
- **[now] Five-reader distribution test (D1)** — [#61](https://github.com/gianlucamazza/mklang/issues/61)

## Next

Doc/schema + release-floor items **shipped** in [#73](https://github.com/gianlucamazza/mklang/pull/73)
([#64](https://github.com/gianlucamazza/mklang/issues/64), [#69](https://github.com/gianlucamazza/mklang/issues/69)–[#72](https://github.com/gianlucamazza/mklang/issues/72) closed). Remaining Now items need live ops or humans:

- **[next]** After Anthropic key + credit: close [#60](https://github.com/gianlucamazza/mklang/issues/60) and re-check release floors
- **[next]** Five-reader distribution test — [#61](https://github.com/gianlucamazza/mklang/issues/61)

### Evidence backlog (harness in, numbers missing — no issue filed yet)

Three measurements are implemented, covered offline, and have **zero live rows**.
They need a maintainer with keys, not more code. Until they run, none of them may
be cited as a finding — and two of them are named falsifiers in
[ADR 0031](./docs/adr/0031-what-would-force-a-language-0-4.md), so the freeze's
exit condition stays unmeasured while they sit here.

- **Boundary corpus + decomposed metrics** — `gate_divergence.py --machines all
  --paraphrase`: cross- vs intra-provider agreement, accuracy against gold
  routes, `gate_blind_spot`, paraphrase invariance
  ([gate divergence](./docs/experiments/gate-divergence.md)).
- **Repair convergence** — `repair_convergence.py --repeats 5`: does the feedback
  make attempt 2 better than attempt 1, or is the budget doing the work
  ([repair convergence](./docs/experiments/repair-convergence.md))?
- **Control-flow-taint incidence** — how many effectful tool states in real
  machines are reachable on a tainted decision (`mklang lint` notes). ADR 0031
  §1 puts the 0.4 trigger at more than one in four.

## Later

Valuable, not in 1.1 (open issues only when ready to pull into a milestone):

- **[later] Truncation `continue` stitching** (ADR 0018)
- **[later] Editor tooling / LSP**
- **[later] Language 0.4 candidates** (each needs ADR + conformance — see BP §16):
  `parse: json` / object, portable `on_truncate`, per-gate `hitl:`, budget split
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

Permanent or deferred-out of the 0.3 stable surface — see
[SPEC §9](./SPEC.md) and [stability guide](./docs/guides/stability.md):
formal types in `structure`, provider/model pinning in `.mkl`, dual-channel
CaMeL control planes (research).

---

## Where we are (language 0.3 / package 1.1.1)

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
- **0.5.1:** showcase honesty (`triage.mkl` real tool states), silent judge-clamp
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
  schema-copy identity test; ADR 0010 (LLM-assisted lint, later Accepted).
- **0.5.4 (release readiness):** reproducible GitHub Release → PyPI Trusted
  Publishing; clean-wheel smoke; DeepSeek + OpenAI blocking live matrix; optional
  provider report; enforceable gate-divergence thresholds.
- **0.6.0:** language **0.3** (`parse: list`, raw whole-template `input:`);
  MCP surface + discovery; machine stdlib (`std_*`); authoring guide.
- **0.7.0:** console M1–M3; MCP live events (ADR 0019); web `search` (ADR 0016);
  output anti-cutoff (ADR 0018); context Layer 0–1 (ADR 0017); `lint --llm`
  (ADR 0010 Accepted).
- **0.8.0:** host tool stub architecture (ADR 0020); console observation honesty
  for truncation; `context.today` host convention; search recency fields; best
  practices guide; OpenAI-compat default `max_tokens=4096`.
- **0.8.1:** host `context.now`; console chrome/content Markdown rendering;
  sectioned produce system (`llm/prompts.py`) + BP §3; agent sticky policy in
  `execution`.
- **0.8.2:** best-practices filesystem/observability guidance, console activity
  glyph cleanup, and optional-dependency CI guard.
- **0.9.0:** XDG/config/discovery phases 1–2 (ADR 0021), responsive Rich CLI and
  console experience (ADR 0022), and connection-error retries.
- **0.9.1–0.9.2:** release-check stabilization followed by clean console
  shutdown with pending provider or human-input work.
- **0.9.3:** documentation alignment for package status, live evidence, and XDG
  session paths.
- **0.10.0:** first-run experience (ADR 0021 phase 3) — `mklang init` seeding
  `hello.mkl`, provider key gate, shell completions, `scripts/install.sh` (pipx),
  the Arch/AUR recipe, and a lean sdist.
- **0.11.0:** global/local config separation (ADR 0023) — per-key `.env`
  layering, `mklang-mcp` config auto-discovery, XDG fallbacks for workspace and
  HITL checkpoints, `mklang doctor`, dead `run:` block and legacy `~/.mklang`
  fallback removed.
- **0.12.0:** class-3 fs data tools (ADR 0024) — `list_files`/`read_file`/
  `write_file` builtins with a coding-tool workspace model — and the
  `std_research` search → ground stdlib machine.
- **0.13.0:** `runtime.yaml` `tools:` block (ADR 0016 completed), process
  logging hygiene (`mklang.*` hierarchy, `--log-level`/`MKLANG_LOG_LEVEL`),
  and the `std_compress` composable stdlib utility.
- **0.14.0:** untrusted-context delimiting (ADR 0025) — provenance taint +
  `<data-NONCE>` fences in produce/judge prompts, normative in SPEC §6 — and
  the CI quality gates: mypy (zero suppressions), coverage `fail_under = 88`,
  ubuntu 3.11–3.13 + macOS + Windows matrix in a reusable `quality.yml`.
- **0.15.0:** console TUI in the core install (textual promoted from the
  `[console]` extra; actionable hint when it is somehow missing), test
  hermeticity against installed-host layers, ADR 0025 follow-up audit
  closed, SECURITY.md + issue/PR templates + dependabot.
- **0.16.0:** quality ratchet (coverage gate 88 → **90**, mypy strict
  tier — add-only — for eleven leaf modules, targeted tests for the three
  weakest modules lifting total coverage to **92%**) and the gate-divergence
  harness widened from one synthetic machine to a **four-machine suite**.
- **1.1.0 (architecture pass):** the gate transition function is **total
  and deterministic given the verdict** — the fused judge may now answer "none of
  the above" instead of being forced to name a condition (SPEC §5 _Totality_),
  with lint requiring a catch-all; **control-flow taint** (ADR 0030) propagates
  provenance onto the *choice* and binds it at the effect surface; the
  gate-divergence harness gained metrics that can fail (boundary corpus, gold
  routes, cross/intra split, paraphrase invariance); `repair` convergence has a
  harness; and the three things that were promising more than they pinned are now
  written down — what a trace attests (SPEC §8), what conformance guarantees
  (`conformance/README.md`), and what would force a language 0.4 (ADR 0031).
- **Live (release 0.14.0 & 0.15.0 matrices):** DeepSeek + OpenAI live smoke
  and cross-provider gate agreement **1.0** green through both release
  pipelines (PyPI Trusted Publishing). Anthropic remains unit-tested; live
  e2e still billing-blocked (credits, not a missing key).

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
  Re-run at suite scale when credits allow; Anthropic still billing-blocked.
- **Shipped:** LLM-assisted lint (`mklang lint --llm`,
  [ADR 0010](./docs/adr/0010-llm-assisted-lint.md), Accepted) — opt-in probe of
  ambiguous / overlapping prose `when` conditions with the real gate judge
  (K synthetic outputs × R judge repeats per multi-gate state). Advisory only:
  never a `--strict` error source, never in the offline CI path.
- **Shipped (multi-provider live, 0.14.0 & 0.15.0 release matrices):** DeepSeek +
  **OpenAI** live smoke and gate agreement green through both release pipelines.
  **Anthropic** adapter remains unit-tested; live e2e blocked by **account
  billing/credits**, not by a missing key (key present; API returns a
  purchase-credits error).

## Organizational

- **Shipped (0.5.0):** docs site (mkdocs-material on GitHub Pages, assembled
  from the repo's canonical markdown) and `mklang lint` (static analysis
  beyond `check`); conformance suite as the language contract (ADR 0009).
- **Shipped:** [best practices](./docs/guides/best-practices.md) — layer discipline
  (language / host / surface), tool contracts, web+time+cutoff checklist,
  anti-patterns, and explicit non-goals for core (bash/FS, knowledge-cutoff magic).
- **Shipped:** community & security hygiene — `SECURITY.md` (private GitHub
  Security Advisories, scope aligned with SPEC §11 — persuasion of fenced
  content and checkpoint-at-rest are documented limitations, not
  vulnerabilities), issue forms (bug asks for a scripted `mklang test` repro;
  feature asks for the layer), a default PR template with the quality-gate
  checklist, and dependabot (grouped uv deps + GitHub Actions, weekly).
- **0.5.4 release path:** a published GitHub Release builds and tests one artifact
  set, requires DeepSeek + OpenAI live agreement, then publishes through PyPI
  Trusted Publishing (OIDC, no long-lived package token). The one-time external
  setup is the `mklang` pending publisher plus the protected GitHub `pypi`
  environment and provider secrets.
- **[later] Editor tooling** — LSP / syntax highlighting beyond the YAML
  schema; `mklang lint` is the first brick.
- **[shipped] Rename `.mk` → `.mkl`** — the `.mk` suffix collided with Makefile
  includes / GitHub Linguist; renamed to `.mkl` (mklang) while adoption is still
  ~nil (hard cut: discovery matches `*.mkl`). The suffix is a discovery
  convention, not a language contract
  ([ADR 0027](./docs/adr/0027-adopt-mkl-extension.md), SPEC §9).

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

## Path to 1.0 (shipped summary)

The 0.13–0.15 cycle shifted from feature growth to **maturity**; 1.0.0 froze the
0.3 surface. Active Now/Next work is at the top of this file (milestone 1.1).

- **[shipped] Path to 1.0 — prep** — SPEC §9 closed; [ADR 0026](./docs/adr/0026-stability-and-deprecation-policy.md),
  [ADR 0027](./docs/adr/0027-adopt-mkl-extension.md); [stability guide](./docs/guides/stability.md).
- **[shipped] Cut 1.0.0** — package 1.0.0, live release gate DeepSeek + OpenAI.
- **[shipped] 1.0.1 validation follow-ups** — authoring-loop `blind_spot = 0.0167`,
  ADR 0028 provisional 1.0 posture, CI format-check + tag↔CHANGELOG; five-reader
  protocol (execution: [#61](https://github.com/gianlucamazza/mklang/issues/61)).
- **[shipped] Showcase refresh** — demos focused on **`agent`** + **`language`**.
- **[shipped] gate-divergence at scale** — four-machine suite DeepSeek + OpenAI;
  dated table in [docs/experiments/gate-divergence.md](./docs/experiments/gate-divergence.md).
  Anthropic third-provider pass: [#60](https://github.com/gianlucamazza/mklang/issues/60).
