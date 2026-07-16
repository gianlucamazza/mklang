# Changelog

All notable changes to mklang are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**Two version lines** are tracked separately:

- **Spec version** — the language, declared per-file via the `mklang:` field
  (currently `"0.2"`).
- **Package version** — the reference interpreter / tooling, SemVer in
  `pyproject.toml` (currently `0.2.2`).

## [Unreleased]

### Fixed

- Docs drift pass: SPEC pseudo-schema includes `hook` / `hooks:`; comparison table and
  philosophy updated for host hooks; ADR 0002/0004 no longer refer to code-hooks as
  future-only; ROADMAP test count aligned (~70).

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
