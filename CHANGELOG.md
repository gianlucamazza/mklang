# Changelog

All notable changes to mklang are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**Two version lines** are tracked separately:

- **Spec version** — the language, declared per-file via the `mklang:` field
  (currently `"0.2"`).
- **Package version** — the reference interpreter / tooling, SemVer in
  `pyproject.toml` (currently `0.5.3`).

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
  `docs/patterns.md`, `conformance/README.md` cross-reference.
  **Deferred:** the CI wiring step (a `.github/workflows/ci.yml` edit running
  `uv run mklang test examples/triage.mk --script examples/triage.test.yaml`) is
  not in this branch — the delivery environment's GitHub App lacks the `workflows`
  permission to push workflow changes. A maintainer must add that step manually;
  the command runs identically today and the scenarios are covered by
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
  `judge:` key in the runtime config — it is now an explicit, opt-in *global*
  override, no longer the default (it ships commented out in
  `config/runtime.example.yaml`). The chosen judge model is recorded in the trace
  as `judge_model` on every `gate_via: llm` step. Gate-divergence numbers
  collected before this change are not comparable with those after; re-run
  `scripts/gate_divergence.py` (now with a `--judge-tier` flag) to refresh them.

### Fixed

- **Strict judge-reply parsing (F2).** The bare-number fallback no longer grabs
  the *first* digit anywhere in the reply (a verbose judge's "Condition 1 fails…"
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
