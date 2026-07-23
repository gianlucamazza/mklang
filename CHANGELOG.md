# Changelog

All notable changes to mklang are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**Two version lines** are tracked separately:

- **Spec version** — the language, declared per-file via the `mklang:` field
  (currently `"0.3"`; `"0.2"` documents remain valid).
- **Package version** — the reference interpreter / tooling, SemVer in
  `pyproject.toml` (currently `0.14.0`).

## [Unreleased]

### Changed

- **The console TUI ships by default**: `textual` moved from the `console`
  extra into the core dependencies, and the Arch PKGBUILD promotes
  `python-textual` from optdepends to depends. The `console` extra remains
  as an empty no-op so `pip install "mklang[console]"` from older docs keeps
  working; `scripts/install.sh` defaults to the `mcp` extra only.

### Fixed

- `mklang console` without `textual` installed now prints the actionable
  install hint again: the hint guarded only the `console.app` import, but
  textual is imported lazily inside `build_app`, so the real failure escaped
  to the generic `ERROR No module named 'textual'` handler.
- The test suite is hermetic against a real mklang installation on the host:
  a pacman/AUR install ships `/etc/mklang` + `/usr/share/mklang` and `mklang
  init --user` creates `~/.config/mklang`, all of which leaked into config
  and machine discovery (CI runners are clean, so only dev machines saw it).
  System paths are module constants now, sandboxed by an autouse fixture.

## [0.14.0] — 2026-07-23

Untrusted-context delimiting (SPEC §6, ADR 0025) and the CI quality gates
(mypy zero-suppression, coverage, multi-platform matrix) — language stays
**0.3**.

### Added

- **Untrusted-context delimiting** (SPEC §6, ADR 0025): the engine tracks
  provenance taint per top-level context key (host inputs, tool observations,
  and every deposit are tainted; author `context:` literals stay trusted) and
  fences tainted interpolations in produce prompts as
  `<data-NONCE>…</data-NONCE>` with a fresh per-call nonce, adding an
  untrusted-data rule to the system message. Judge prompts (shared
  `build_judge_user`, deduplicated across adapters) always fence
  OUTPUT/REASONING/CONTEXT. Taint survives checkpoints (`"tainted"` frame
  field; missing field resumes all-tainted) and resume-injected values are
  tainted. New: `run(..., delimit=..., trusted_keys=...)`, scenario `input:`
  key, four `taint-*` conformance cases, `tests/test_taint.py`.

- CI quality gates: static type checking with **mypy** (zero suppressions —
  `check_untyped_defs`, `disallow_incomplete_defs`, `strict_equality`, warn
  flags; every function in `src/mklang` is annotated) and **coverage** via
  pytest-cov with a `fail_under = 88` gate (90.2% measured at introduction).
- CI test matrix: Python 3.11/3.12/3.13 on ubuntu plus macOS and Windows legs
  (3.13), with the console extra installed so Textual tests run in CI. The
  shared checks live in a reusable `quality.yml` workflow called by both
  `ci.yml` and `release.yml` (pinned to the release tag).

### Changed

- **Behavior change:** produce prompts of machines fed host inputs or tool
  observations now carry `<data-NONCE>` fences and one extra system
  paragraph; judge user messages always fence their data sections. Machines
  interpolating only author literals are byte-identical. Escape hatch:
  `run(..., delimit=False)` (produce side only).
- Engine transition step now halts with explicit `state-error:
gate-missing-to` / `repair-missing-budget` labels when a hand-built
  `Machine` bypasses schema validation (schema-validated machines are
  unaffected — the schema already requires `to` and a repair budget).

### Fixed

- The atomic replace in the fs write path retries transient Windows sharing
  violations (concurrent `os.replace` onto the same target) — caught by the
  new Windows CI leg; POSIX behavior unchanged.

## [0.13.0] — 2026-07-23

Declarative tool-backend bindings, process logging hygiene, and the
`std_compress` stdlib machine — language stays **0.3**.

### Added

- `std_compress` — composable working-memory compression in the stdlib
  (ADR 0017 Layer 1): one judge-verified compress state (repair ×1) any
  machine can `call:` mid-loop to rewrite an accumulator short. Contract:
  `task` + `notes` → `answer`; notes are marked untrusted in the prompt.
- Optional `tools:` block in `runtime.yaml` (ADR 0016): declarative backend
  bindings for the builtin host tools — `tools.search.backend`
  (`stub|fake|tavily`), `tools.kb.backend`, `tools.mail.backend`, and
  `tools.fs.{backend, workspace, write}`. Precedence per knob: programmatic
  `configure_*()` > explicit `MKLANG_*` env var > config > built-in default
  (so `tools.search.backend: stub` is a persistent off-switch that beats the
  `TAVILY_API_KEY` auto-select). No `api_key` knob by design — secrets stay
  in the layered `.env` (ADR 0023).
- `mklang doctor` reports each tool backend **with its deciding source**
  (`env` / `config` / `default`) through the same resolvers the runtime
  uses, instead of re-deriving state from the environment.

- Process logging hygiene (best practices §12): the host now logs on the
  `mklang.*` logger hierarchy to stderr — `--log-level` on every CLI
  subcommand and `mklang-mcp`, or `MKLANG_LOG_LEVEL` (flag wins; default
  `warning`, format `LEVEL name: message`, no timestamps). Host logs never
  ride MCP logging notifications.

### Changed

- A _set_ `MKLANG_FS_WRITE` now decides the write grant either way:
  `MKLANG_FS_WRITE=0` is an explicit off that beats a config
  `tools.fs.write: true` (previously a falsy value was indistinguishable
  from unset). `--allow-write` still beats everything.
- Plugin/stdlib load failures (machines, hooks, providers, tools) and the
  resume ops advisories (`--force` hash divergence, non-increasing cost
  budget) are `WARNING mklang.<module>: …` log lines instead of ad-hoc
  `# warning:` stderr prints. Message bodies are unchanged.

### Fixed

- The fs data tools' "INFO audit line" (0.12.0) was never visible: no
  handler existed, so INFO records were dropped. The audit lines are now
  real — run with `--log-level info` to see them.

## [0.12.0] — 2026-07-23

Filesystem data tools ([ADR 0024](./docs/adr/0024-fs-data-tools.md)) and the
`std_research` stdlib machine — language stays **0.3**.

### Added

- `list_files` / `read_file` / `write_file` builtin host tools (`mklang.fs`)
  with a coding-tool workspace model: reads live by default, confined to a
  workspace resolved as `--workspace` > `MKLANG_FS_ROOT` > cwd; disk writes
  need an explicit grant (`--allow-write` / `MKLANG_FS_WRITE=1` / console
  consent). Relative paths only, dotfile and escape refusal after resolve
  (re-checked on the resolved target, so symlinks cannot smuggle targets in
  or out), size caps, data-suffix allowlist (never `.mk`), atomic 0600
  writes via unique tempfiles, INFO audit line. `MKLANG_FS_BACKEND=stub` is
  the offline off-switch.
- `mklang run` and `mklang-mcp` gain `--workspace` / `--allow-write`;
  `mklang doctor` reports the resolved workspace and write grant; the
  console asks consent once per session for writes.
- `std_research` — search → ground stdlib machine over the bundled
  [ADR 0016](./docs/adr/0016-host-web-search-tool.md) `search` tool:
  `plan_query → search (accumulate) → check → {loop | finalize | no_search}`.
  Answers only from search observations (prompts mark them as untrusted
  content), with a grounding repair gate at reasoning tier and an honest
  `no_search` state when no backend is bound; dogfoods host-filled
  `context.today`. Ships scripted scenarios like the rest of the stdlib.

## [0.11.0] — 2026-07-18

Global vs local configuration separation
([ADR 0023](./docs/adr/0023-global-local-config-separation.md)) — language
stays **0.3**.

### Added

- `mklang doctor` — diagnose the resolved setup: winning config file and layer
  (project / user / system / bundled), schema validation of the resolved config
  (stale keys surface as warnings), which `.env` files loaded, per-provider
  key status (active-provider gaps are errors, `local` exempt), tool backends
  (`search`/`kb`/`mail`), machine roots with counts, and the state paths.
  Exit 1 when the active provider cannot run.
- `mklang init --user` now also copies `runtime.schema.json` next to the user
  `runtime.yaml` (parity with project mode; editor validation works in both).
- `run --hitl` without `--checkpoint` suspends into
  `$XDG_STATE_HOME/mklang/checkpoints/` instead of erroring; the suspension
  message prints the generated path.

### Changed

- `.env` now layers **per key**: real environment > project `.env` > user
  `~/.config/mklang/.env`. Previously any project `.env` hid the user file
  entirely, even for keys it did not define.
- `mklang-mcp` resolves its config through the same chain as the CLI
  (project → user → `/etc` → bundled) instead of pinning the checkout-relative
  bundled example — MCP clients no longer need an explicit `--config`.
- The console workspace defaults to `./machines` only when it exists, falling
  back to the XDG user machines dir seeded by `mklang init --user`.

### Removed

- The dead `run:` block (`max_repair_per_gate`, `trace`) from the example
  config and its schema: the runtime never read it — repair budgets live in
  each gate (`repair: N`, SPEC §7) and the trace is always part of the run
  result. `mklang doctor` flags it as a stale key in existing configs.
- The legacy `~/.mklang/console/sessions` read fallback: sessions live only
  under the XDG state root (ADR 0021's migration window is over).

## [0.10.0] — 2026-07-18

First-run experience (language stays **0.3**).

### Added

- [Getting started guide](./docs/guides/getting-started.md) — one linear
  install → init → key → console path, first in the docs nav.
- `mklang --version`, and a getting-started nudge (exit 0) on bare `mklang`
  instead of a usage error.
- `mklang init` seeds `machines/` with a commented `hello.mk` sample and its
  `hello.test.yaml` scenario script (keyless first run via `mklang test`).
- Upfront provider key gate: runs, the console, and `lint --llm` fail fast
  with the exact `.env` variable to set instead of dying inside the provider
  SDK (`local` stays exempt).
- Shell completions via argcomplete (`[completions]` extra).
- ADR 0021 phase 3 packaging: `scripts/install.sh` (pipx + `mklang init
--user`, with `--uninstall`) and an Arch Linux recipe in `packaging/arch/`;
  the optional MCP user service is deferred (stdio-only server).

### Changed

- README install/quickstart restructured: pipx path first, checkout/`uv`
  workflow kept as the from-checkout section.
- Lean sdist: exclude media assets, `site/`, `demos/`, `dist/`, and `.github/`
  from the source distribution (the AUR recipe builds from it).

## [0.9.3] — 2026-07-17

Documentation-alignment patch (language stays **0.3**).

### Fixed

- Make the best-practices guide the documentation SSOT for current XDG host
  paths and console lifecycle behavior.
- Align the console session path with ADR 0021 while retaining the legacy path
  as a documented read fallback.
- Bring the README live-matrix status and roadmap history up to date through
  the 0.9.2 release, and mark ADR 0015's original path as superseded.

## [0.9.2] — 2026-07-17

Console shutdown patch (language stays **0.3**).

### Fixed

- Shut down the console cleanly when `Ctrl+C` is pressed during an active run:
  request cooperative cancellation, release pending human prompts, close the
  provider client, and wait for the backing thread before returning to the shell.
- Prevent late UI callbacks and session writes after console shutdown starts.

## [0.9.1] — 2026-07-17

Release-pipeline patch (language stays **0.3**).

### Fixed

- Keep fatal CLI diagnostics on one stable line when stdout/stderr is not a TTY.
- Skip the console-session CLI test when the optional Textual extra is absent.

## [0.9.0] — 2026-07-17

Feature release (language stays **0.3**). Every local surface now works outside
a repository checkout, preserves automation-safe output, and presents a
responsive operational workspace in the terminal.

### Added

- **Responsive console and CLI presentation (ADR 0022).** Rich human output with
  stable piped JSON, shared diagnostics, responsive inspector/activity layout,
  slash-command quoting/suggestions, operational status, cooperative stop, and
  additive `run-finished` events.
- **ADR 0021 phases 1–2.** XDG host paths, bundled config fallback,
  idempotent `mklang init`, legacy console-session reads, and system/user/project
  machine discovery with source labels.

### Fixed

- **Connection errors now retry.** Provider `_create` loops treated only HTTP
  `TRANSIENT_STATUS` as retryable; SDK connection failures carry no
  `status_code`, so a network blip halted the run with `provider-error` on the
  first try. `is_connection_error` (matched by class name — the SDKs are
  lazy-imported) classifies `APIConnectionError` / `APITimeoutError` as
  transient with the same exponential backoff, for both the Anthropic and
  OpenAI-compat adapters.

## [0.8.2] — 2026-07-17

Package patch (language stays **0.3**). Documentation growth (best practices
§12–§13) plus a console glyph fix and a CI test guard.

### Added

- **Best practices §12–§13** — observability (trace vs live events vs process
  logging) and filesystem taxonomy (host paths / workspace `.mk` / data tools /
  no bash in core). Cross-links from console security and patterns.

### Fixed

- **Console activity tree double expand icon.** Run rows no longer prefix `▶ `
  in the label — Textual Tree already draws the ▶/▼ toggle.
- **CI: console render tests skip without `rich`.** `test_console_render.py`
  now uses `pytest.importorskip("rich")` like the other console tests, so the
  no-console-extra CI matrix collects cleanly.

## [0.8.1] — 2026-07-17

Package patch (language stays **0.3**). Console rendering safety, host wall-clock,
and produce system-prompt assembly — surface/host polish only.

### Added

- **Host clock convention `context.now`.** When a machine declares top-level
  `now` and it is still empty after inputs, CLI / MCP / console fill a local
  ISO datetime with offset (same opt-in pattern as `today`). Console
  `agent.mk` declares `now` and is instructed to REPLY wall-clock questions
  from the host values (no AUTHOR for the clock alone).
- **Produce system prompt assembly** (`llm/prompts.py`): sectioned system
  message from `structure` + `execution`; documented as Best practices §3
  (system vs user). Console `agent.mk` puts sticky policy in `execution` and
  turn data in `prompt`.

### Changed

- **Console conversation rendering (chrome vs content).** Agent replies render
  as CommonMark in the log; user/HITL text and slash observations stay plain or
  fenced (`json` / `yaml`). Activity tree turn titles, machine names, and
  output previews use plain styled `Text` (no Rich-markup injection). Helpers
  live in `console/render.py`; log uses `markup=False`.
- **Docs:** SPEC §4–§6 non-normative notes (produce system/user assembly, host
  clocks); Best practices §3; authoring faces table; console brain prompt
  assembly; README faces/status; ADR 0016 `now` checklist.

## [0.8.0] — 2026-07-17

Package feature release (language stays **0.3**). Host tools gain a uniform stub
architecture; console anti-cutoff observations stay honest; time-sensitive
machines get a host `today` convention and richer search.

### Fixed

- **Console `run_machine` observation honesty (anti-cutoff chain).** Produce
  truncation (ADR 0018) is propagated as `truncated` / `finish_reason` plus a
  compact `trace` summary; long results are clipped with an explicit
  `…[truncated]` marker and `result_truncated` — no more silent 2k cuts that
  invited the brain to invent the missing tail.

### Added

- **Host convention `context.today`.** When a machine declares top-level
  `today` and it is still empty after inputs, CLI / MCP / console fill the
  host ISO date (`YYYY-MM-DD`). Never invents undeclared keys.
- **Search recency fields** (ADR 0016 addendum): optional tool inputs `days` /
  `topic`; optional `published_date` on results (Tavily when provided).
- Research / news patterns and `agent.mk` instruct grounding in notes/today and
  forbid filling gaps with pre-training knowledge; console docs document the
  observation shape.
- **Best practices guide** (`docs/best-practices.md`) — layer discipline, authoring
  checklist, recommended tool contracts, web/time/cutoff rules, anti-patterns,
  and what must stay host-side vs candidate language 0.4.
- **Host tool stub architecture** (ADR 0020): shared JSON envelope
  (`tool` / `stub` / `error`) for I/O tools; `search_kb` and `send_reply` use
  structured observations; default `send_reply` has `sent: false` (no fake
  delivery); fake backends via `MKLANG_KB_BACKEND` / `MKLANG_MAIL_BACKEND` and
  `configure_kb` / `configure_mail`; modules `tool_obs`, `kb`, `mail`.
- **`news_search` scenario tests** (`examples/news_search.test.yaml`) — happy path
  and search-unbound → `no_search`.
- OpenAI-compatible produce defaults **`max_tokens=4096`** when tier params omit
  it (parity with Anthropic; reduces silent length stops; still overridable /
  droppable per provider).

### Changed

- **Breaking (host observation shape only):** builtin `search_kb` / `send_reply`
  no longer return free-text `[kb stub]…` / `[sent]…` strings — they return ADR
  0020 JSON. Scripted scenario tools are unaffected. `search` adds `tool` +
  `stub` fields (additive).

## [0.7.0] — 2026-07-17

Package feature release (language stays **0.3**). Console becomes a full
operational front door; host tools and runtime budgets close the agent loop.

### Added

- **Console M1–M3** (ADR 0015 Accepted). Agent-first Textual TUI
  (`mklang[console]`) whose brain is the bundled, user-swappable `agent.mk`:
  authoring loop (write → validate → repair), persistent sessions
  (`--continue` / `--session`), budget-exhaustion park/`/resume`, live activity
  tree, F2 inspector, slash commands. Docs: `docs/console.md`.
- **Live engine events on the MCP transport** (ADR 0019): `run`/`resume` stream
  `on_event` as `mklang.event` logging notifications.
- **Web search tool** (ADR 0016 Accepted): structured JSON `search` observations;
  offline stub by default; opt-in `fake`/`tavily` backends;
  `examples/research_web.mk` + scenario tests.
- **Output anti-cutoff** (ADR 0018 Accepted): `Produced.truncated` / `finish_reason`;
  trace + events; `report`|`halt` on CLI (`--on-truncate`), MCP, console,
  scripttest. Truncated `parse: list` → `parse-list-truncated`.
- **Context management Layer 0–1** (ADR 0017 Accepted): judge CONTEXT head+tail
  marker; produce-prompt per-value cap; console `history_for_brain`; compress
  pattern `examples/research_compress.mk`.
- **LLM-assisted lint** (`mklang lint --llm`, ADR 0010 Accepted): advisory only.

## [0.6.0] — 2026-07-17

The language moves to **0.3** (additive; every 0.2 document remains valid) and
the agent-facing surfaces land: MCP host, machine stdlib, discovery, authoring
guide.

### Added — language 0.3 (ADR 0014)

- **`parse: list`** — a generative state can deposit a parsed JSON array
  (markdown fences tolerated) instead of text; unparseable output halts cleanly
  with `state-error: parse-list`. This makes Plan-and-Execute a pure machine.
- **Raw whole-template `input:` resolution** — an `input:` value that is exactly
  one `{{path}}` placeholder passes the raw context value (lists included)
  across `call:`/`tool:` boundaries; mixed templates render as before.
- Conformance cases `parse-list`, `parse-list-invalid`, `raw-input-passthrough`;
  the JSON Schema (both copies) gains the `parse` enum; `check` warns when a 0.2
  document uses the new face.

### Added — surfaces

- **MCP server surface** (ADR 0011, now Accepted). Optional stdio MCP host —
  extra `mklang[mcp]`, console script `mklang-mcp` — exposing exactly two tools:
  `run` (machine as inline `.mk` source or filesystem path, `inputs` merged into
  the context, optional `cost_budget`/`hitl`) and `resume` (opaque single-use
  checkpoint handle, HITL reply injection, new budget). Results return the same
  `{status, error, result, usage, trace, at?}` shape the CLI prints. Suspended
  runs hold their frames in a process-scoped in-memory session store; nothing is
  written to disk. Core install is unaffected (`mcp` is not a core dependency).
- **Public host seam** `mklang.host` — `prepare_path` / `prepare_source` (inline
  source loading is new) / `build_output` / `set_path`, with structured
  `PrepareError` instead of printed diagnostics. The CLI now wraps this seam, so
  CLI and MCP semantics cannot drift.
- **Agent authoring guide** (`docs/authoring.md`) — a compact recipe for writing
  a correct `.mk` with the `check`/`lint` loop, distilled from SPEC with the real
  validator messages.
- **Machine stdlib** (ADR 0012). Eight general-purpose architecture machines
  bundled with the package — `std_cot`, `std_self_consistency`, `std_refine`,
  `std_tot`, `std_debate`, `std_map_reduce`, `std_cascade`,
  `std_plan_execute` — uniform contract (`task` in, `answer` out), each with
  scripted scenario tests. Present in every host registry with
  user-always-wins precedence (stdlib ← `mklang.machines` entry-point plugins ←
  siblings ← target, shadowing warned); runnable **by name** from CLI and MCP
  (`mklang run std_cot --set task="…"`); inline MCP sources can `call: std_*`.
  Run-by-name checkpoints record a null machine hash and resume cleanly.
  Catalog in `docs/stdlib.md`.
- **Discovery, check, durable resume** (ADR 0013). MCP tools `list_machines` /
  `describe_machine` (what may be commissioned, with full contracts), `check`
  (schema + semantics + lint as structured output, no provider needed), and
  `checkpoint_path` on `run`/`resume` for cross-process durable suspensions —
  `resume` accepts an in-memory handle or a checkpoint file, including files
  from `mklang run --checkpoint`; inline sources persist via a new optional
  `machine_source` envelope key. CLI gains the symmetric `mklang machines`
  subcommand (JSON; `--dir` adds project machines).

### Changed

- CI runs the unit suite with the `mcp` extra (the MCP tests no longer skip
  silently) and checks/lints the bundled stdlib alongside the examples.
- Unknown run-by-name targets fail with the list of bundled machine names
  instead of a raw errno message.
- `# noqa` annotations removed across the codebase (the suppressed rule was
  never enabled); explanatory comments remain.

## [0.5.4] — 2026-07-16

Release-readiness pass. The language stays **0.2** and runtime semantics are
unchanged; this release makes the existing interpreter reproducibly distributable.

### Added

- **Trusted Publishing release workflow.** A published GitHub Release now gates
  publication on the full offline suite, strict docs, artifact validation, a
  clean-wheel installation smoke, and the live provider matrix. The publish job
  consumes the already-tested artifacts and uses short-lived PyPI OIDC credentials.
- **Enforceable live-matrix reporting.** `scripts/gate_divergence.py` can require
  named providers, enforce a minimum agreement rate, write a summary artifact,
  and distinguishes a missing-key skip from a provider/runtime failure.
- **Release provenance tests.** CI pins package metadata and `mklang.__version__`
  to the same value and tests the required-provider gate offline.

### Changed

- DeepSeek and OpenAI are the blocking release providers (three divergence runs,
  agreement `1.0`). Anthropic, Google, OpenRouter, xAI, and Mistral are attempted
  when credentials are configured and remain informational.

## [0.5.3] — 2026-07-16

Third remediation pass (Follow-up 003): closes the residue Remediation 002
delivered without declaring. The language stays **0.2**; no `.mk` needs changes.

### Added

- **`mklang test` — deterministic machine testing without API keys (R3-1).**
  A new subcommand runs a machine against a script of named scenarios with a
  **scripted LLM** (produce texts + judge picks) and scripted tools/hooks —
  fully deterministic, no provider or key. Per-scenario PASS/FAIL with a minimal
  diff (first mismatched key, expected vs actual); exit 0 iff all pass. The
  scripted LLM, `hooks:`/`tools:` bindings, and expectation matcher now live once
  in `src/mklang/scripttest.py`, shared with the conformance runner (all 21 cases
  green through it, unchanged). Ships `examples/triage.test.yaml` (happy path +
  KB-empty escalation). Docs: README "Test your machine without API keys",
  `docs/patterns.md`, `conformance/README.md` cross-reference. CI runs
  `uv run mklang test examples/triage.mk --script examples/triage.test.yaml`
  in the unit-test job (no API keys); the same scenarios are also covered by
  `tests/test_scripttest.py` in the normal pytest run.
- **Static budget-feasibility check (R3-2).** `mklang check`/`lint` now BFS the
  shortest path (in states) from `entry` to a gate `to: END`. `budget` below it is
  a guaranteed `budget-exhausted` halt, reported as error `budget-infeasible`;
  `budget < shortest + 2` warns (no headroom for a single repair). Fan-out states
  count as 1 (branch counts are data-dependent), so the check is a lower bound —
  the message says so. SPEC §7 documents it next to the charging rule. Host
  pre-validation only; run semantics unchanged.
- **Dotted second-segment lint on inline context maps (R3-3, completes F7).** When
  a `{{root.key}}` root resolves to an inline dict literal in `context:`
  (`ticket: {body: …}`), the second segment is now validated against the map's
  keys, so `{{ticket.bod}}` is flagged. Skipped for state outputs and runtime
  roots (`human`/`item`/`index`) whose shape is unknowable; deeper than segment 2
  stays out of scope.
- **Schema-copy identity test (R3-4).** One test asserts `schema/mklang.schema.json`
  and the packaged copy `src/mklang/data/mklang.schema.json` are byte-identical,
  with a failure message naming the sync direction (repo `schema/` is the source).
- **ADR 0010 — LLM-assisted lint (R3-5, Proposed, design only).** An opt-in
  `mklang lint --llm` that would generate synthetic outputs and measure
  gate-selection stability/overlap (reusing `gate_divergence.py`) to catch
  ambiguous prose `when` conditions. Documents cost model, determinism caveats,
  relation to the conformance suite, and why it is out of 0.5.x. No code.

## [0.5.2] — 2026-07-16

Second remediation pass. The language stays **0.2**; no `.mk` needs changes.

### Changed (observable behavior)

- **Default judge model now follows each state's tier (F1).** Previously every
  gate — including the highest-stakes gates on `reasoning` states (refund
  thresholds, legal matters, human escalation) — was judged by the cheapest
  (`fast`) model, silently deviating from SPEC §2.1. Gate judging now uses the
  state's own effective tier by default. **This changes which model judges your
  gates.** To restore the previous single-model behavior, set the provider
  `judge:` key in the runtime config — it is now an explicit, opt-in _global_
  override, no longer the default (it ships commented out in
  `config/runtime.example.yaml`). The chosen judge model is recorded in the trace
  as `judge_model` on every `gate_via: llm` step. Gate-divergence numbers
  collected before this change are not comparable with those after; re-run
  `scripts/gate_divergence.py` (now with a `--judge-tier` flag) to refresh them.

### Fixed

- **Strict judge-reply parsing (F2).** The bare-number fallback no longer grabs
  the _first_ digit anywhere in the reply (a verbose judge's "Condition 1 fails…"
  misread as choice 1). Parse order is now: strict JSON, then a whole-reply bare
  number, then the **last** number in the reply (models conclude with the answer).
  The last two are traced as `judge_parse` (anomaly-adjacent, not a fallback). The
  judge system prompt now forbids extra numbers; SPEC §5 constrains conformant
  judges to terse instruct-style replies.
- **`sample` branch diversity (F3).** Each `sample: N` branch now sees its own
  `{{index}}` (0-based), so a prompt can say "you are branch {{index}}, take a
  different approach" (Tree-of-Thought, debate) instead of relying on temperature
  alone. `{{index}}` is now available in both fan-out forms; `{{item}}` remains
  `over`-only.

### Added

- **`unresolved-interpolation` lint rule (F7).** `mklang lint` flags any `{{path}}`
  whose first segment no `context:` key / state `output:` / (inside a fan-out)
  `item`/`index` provides — the silent-typo bug (`{{kb_answr}}` → empty string).
  `item`/`index` referenced outside a fan-out state are flagged too. First-segment
  only (dotted tails can't be checked statically); warning by default, error under
  `--strict`.
- **`--strict` rejects unsupported `mklang:` versions (F6).** An unknown language
  version stays a warning by default but becomes a hard error (`version-unsupported`)
  under `mklang check --strict` / `lint --strict` / the new `run --strict`.
- **`0600` checkpoints (F5).** Checkpoint files (full blackboard as plaintext JSON)
  are written owner-only. SPEC §11 now lists checkpoints as an asset and documents
  the plaintext-at-rest surface (host-side mitigation; encryption is a v0.2
  non-goal). The `--checkpoint` help notes the plaintext content.
- **Conformance coverage for hook precedence and `tool` states (F8).** The case
  format gains scripted `hooks:` (boolean sequences) and `tools:` (list or
  `{input-substring: output}` map) bindings, plus `expect.error_prefix`. New cases:
  `hook-before-prose`, `hook-false-falls-through`, `tool-state-output-deposit`,
  `tool-unknown-halts`, `fanout-sample-index` (F3), `budget-fanout-charging` (F4).
  Suite: 15 → 21 cases.
- **SPEC §7** now states the fan-out step-charging rule (`max(1, len(branches))`)
  explicitly, with the map-reduce budget-sizing implication and a worked example;
  `docs/patterns.md` and ROADMAP note the possible v0.3 `budget`/`branch_budget`
  split.

> **Deferred from Remediation 002, delivered in 0.5.3:** author-facing scripted
> testing (`mklang test`), budget-feasibility check, dotted-segment lint,
> schema-identity test, ADR 0010.

## [0.5.1] — 2026-07-16

### Fixed

- **Judge silent clamp** — out-of-range or 0-based `{"choice": k}` replies are
  no longer clamped to a valid gate. `parse_choice` returns `None` for OOR;
  adapters raise `JudgeUnparseable`; the engine does not re-clamp. Soft-fallback
  to `otherwise` (or hard-halt `judge-unparseable`) is traced via
  `judge_fallback` / `judge_raw` — never a mute misroute with only `gate_via: llm`.
- **Showcase honesty (`triage.mk`)** — `search_kb` and `send_reply` are real
  `tool:` states (host stubs); generative states no longer claim tool use or
  “confirm the send.” Same honesty pass on `research.mk` (no fake `web_search`).
- **README** — dropped “no host code required”; documented that tools/hooks are
  host-supplied; centered conformance + portable spec as the differentiator.

### Added

- Builtins / entry points: `search_kb`, `send_reply` (deterministic stubs).
- **SPEC §5** — normative 1-based judge protocol; OOR = anomaly; documented
  `JUDGE_CONTEXT_CHARS` (4000) truncation.
- **SPEC §11 Threat model (v0.2)** — injection surface, partial mitigations,
  explicit non-goals (declare rather than deny).
- Reference produce temperature defaults documented (non-normative).
- **Gate-divergence experiment** — `scripts/gate_divergence.py` +
  `docs/experiments/gate-divergence.md` (cross-provider agreement scaffold).
- ADR 0004 honesty note: prose-gate reliability is empirical.

### Changed

- Positioning: “writable by non-programmers” softened to prose-first / readable;
  production needs developer judgment for tools, hooks, and untrusted inputs.

## [0.5.0] — 2026-07-16

### Added

- **Conformance suite** (ADR 0009) — `conformance/cases/*.yaml`:
  implementation-neutral cases (machine + scripted LLM + expected outcome) that
  pin the language semantics; any second interpreter must pass them with its own
  runner. Reference runner in `tests/test_conformance.py` (15 cases).
- **`mklang lint`** — `check` plus static analysis: dead gates after
  `otherwise`, repair-only states, outputs nobody reads (terminal/judged states
  exempt), template roots nothing provides (`--strict` exits 1 on findings).
- **Provider adapters as entry-point plugins** — group `mklang.providers`
  (factory `(ProviderConfig) -> LLM`); builtin `anthropic`, unknown names fall
  back to the OpenAI-compatible adapter. Completes the plugin story
  (tools/hooks/providers).
- **Gated live smoke tests** (`tests/test_live.py`) — opt-in via `MKLANG_LIVE=1`,
  provider-agnostic: they run the config's `active` provider (override with
  `MKLANG_LIVE_PROVIDER`) and skip when its key is missing. All providers,
  Anthropic included, share the same path — no provider-specific test code.
- **CI + docs site** — extended GitHub Actions workflow (tests, ruff, schema +
  semantic checks, lint, build, gated live smoke on main) and an mkdocs-material
  site assembled from the repo's canonical markdown (`scripts/build-docs.sh`,
  deployed to GitHub Pages).

### Changed

- SPEC termination paragraph: the END-reachability validator is enforced (it
  already was — the prose still said "SHOULD").
- Packaging metadata: classifiers, corrected repository URLs, author contact.

## [0.4.0] — 2026-07-16

### Added

- **Human-in-the-loop** (ADR 0008) — with `--hitl` (requires `--checkpoint`), a
  fired `escalate` gate **suspends** at the handler state instead of just routing:
  the envelope records `reason: "escalated"` and `hitl: true`. Reply via
  **`mklang resume ck.json --set human.reply="…"`** — values land in the innermost
  frame's context so the handler can interpolate `{{human.reply}}`. Library API:
  `run(..., escalate_suspend=True)`; mutate `frames[-1]["ctx"]` before resuming.
  Default off — escalate-as-routing (tier cascades) is unaffected; escalate to
  `END` and fan-out branches never suspend. Language unchanged (spec stays 0.2).

## [0.3.0] — 2026-07-16

### Added

- **Resumable runs / checkpoints** (ADR 0007) — opt-in: with `--checkpoint PATH`,
  budget exhaustion (`budget-exhausted` / `cost-exhausted`) **suspends** instead of
  halting and writes a JSON checkpoint (frames = blackboard + position + spend per
  `call` level, machine sha256). New subcommand **`mklang resume <checkpoint>`**
  (`--max-tokens`, `--machine`, `--force`) continues as if uninterrupted — golden
  round-trip tested, nested `call` included. New `RunResult` status `"suspended"`
  with `frames`; library API `run(..., suspendable=, resume=)`; CLI exit code 3.
  Fan-out branches never suspend. Language unchanged (spec stays 0.2).

### Fixed

- Docs drift pass: SPEC pseudo-schema includes `hook` / `hooks:`; comparison table and
  philosophy updated for host hooks; ADR 0002/0004 no longer refer to code-hooks as
  future-only; ROADMAP test count aligned (~70).
- Stale `__version__` in `mklang/__init__.py` (was pinned at 0.2.0).

## [0.2.2] — 2026-07-16

### Added

- **Code-hook gates** — optional `hook: <name>` on a gate evaluates a host predicate
  `(context, output) -> bool` without the LLM (ADR 0006). Top-level `hooks:`
  declarations; CLI builtins (`auto_approve_ok`, …); example `hook_gates.mk`. Trace
  records `gate_via: hook|llm|otherwise`.
- **Tool / hook plugin registry** — entry-point groups `mklang.tools` and
  `mklang.hooks`; `load_tool_registry()` / `load_hook_registry()` merge builtins with
  third-party plugins (later keys win). Documented in CONTRIBUTING / patterns.

### Changed

- Default runtime provider is **DeepSeek** (`active: deepseek` in
  `config/runtime.example.yaml`); README quickstart and status aligned. Live smoke
  re-verified on DeepSeek (`expense_approval.mk` → `done`).

## [0.2.1] — 2026-07-16

Correctness hardening and multi-provider polish on top of the v0.2 core.

### Fixed

- **Sub-machine halt propagation** — a `call` whose child halts (budget, fail, …)
  now halts the parent as `call-failed: <child-error>` with nested `sub_trace`,
  instead of continuing as `done` with `result=None`.
- **Judge sees reasoning** — when `reason: true`, the private chain-of-thought is
  passed to `LLM.judge` (SPEC §4.5 / §6), not only recorded in the trace.
- **Anthropic adapter parity** — transient retry with backoff, wrap API failures as
  `ProviderError`, apply `temperature` when thinking is off, structured JSON judge
  (shared `parse_choice` with OpenAI-compat).
- **Pre-run tier validation** — `mklang run` rejects machines that need a tier missing
  from the provider map; engine KeyError messages name the missing tier.
- **Shared `cost_budget` across `call`** — sub-machines inherit the remaining token
  budget (no unbounded child spend while the parent still looks under budget).
- **Judge unparseable is no longer silent** — adapters raise `JudgeUnparseable`; the
  engine soft-falls back only to an eligible `otherwise` (trace: `judge_fallback`),
  else halts with `judge-unparseable`.
- **`over` missing path / wrong type** — hard error (empty list still OK per SPEC).
- **Fan-out branch `call` halt** — preserves `sub_trace` and child token usage.
- Engine exception-safety (clean `halt`, isolated fan-out branches); empty-`eligible`
  no longer crashes; `--set` accepts JSON (lists for `over`); `load_registry` skips
  malformed siblings; `.env` discovered from cwd.

### Added

- **Formal `tool` states** — a state can invoke a host-registered callable so tool
  observations re-enter the context (real ReAct, not prose-simulated). Optional
  top-level `tools:` block; built-in demo tools (`calc`, `search`).
- **Cost accounting** — per-step token usage in the trace, a run total, and an
  optional `cost_budget` (halt `cost-exhausted`).
- **Error taxonomy** — `refusal`, `provider-error`, `call-failed`,
  `judge-unparseable` halt reasons; typed adapter exceptions (`CallFailed`,
  `JudgeUnparseable`, …).
- **Structured-output judge** — OpenAI-compatible and Anthropic adapters judge via
  JSON `{"choice": N}` with a regex fallback path in `parse_choice`.
- Per-tier `params` applied to the model (effort / thinking / reasoning_effort),
  best-effort with drop-on-error; pre-run validation in `mklang run`; richer
  `mklang check` (dead states, unproduced `result`, catch-all warning, version
  advisory).
- Schema bundled as package data; `mklang: "0.2"` field; transient-error retry.
- Apache-2.0 `LICENSE`, `CONTRIBUTING.md`, this changelog.
- Quality: golden-trace and cookbook-conformance tests; Anthropic adapter unit tests
  (params / refusal / usage / retry / judge). **Live Anthropic e2e still deferred**
  (no `ANTHROPIC_API_KEY` in the release environment). Live-tested path remains
  DeepSeek.
- Docs: SPEC header aligned to **0.2**; ROADMAP shipped items synced.

## [0.2.0] — core v0.2 + reference interpreter

### Added

- **Language core v0.2**: `reason` (traced chain-of-thought), `accumulate`
  (list-append), fan-out (`sample` / `over`), sub-machine `call`, top-level `result`.
- Patterns cookbook (`SPEC.md §10`) mapping CoT / ReAct / Reflexion / Self-consistency
  / Tree-of-Thought / Plan-Execute / Debate / Map-Reduce / Router / speculative cascade.
- **Reference interpreter** (`src/mklang/`): loader + validator, `{{}}` interpolation,
  multi-provider LLM adapters (native Anthropic + generic OpenAI-compatible), run loop,
  nested trace, `mklang run` / `mklang check` CLI. Live-tested on DeepSeek.
- JSON Schema `oneOf {generative | call}`; examples `self_consistency`, `map_reduce`
  (+ `summarize_doc`), `react`.

## [0.1] — language definition

### Added

- The mklang concept: an LLM-driven state machine where each state has four faces
  (`structure`, `prompt`, `execution`, `gates`), gates are transitions, and the LLM is
  the runtime. Provider-agnostic capability tiers (`fast` / `balanced` / `reasoning`).
- `SPEC.md`, JSON Schema, multi-provider runtime config, examples `triage`, `research`,
  `expense_approval`.
