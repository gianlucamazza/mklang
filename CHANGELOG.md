# Changelog

All notable changes to mklang are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**Two version lines** are tracked separately:

- **Spec version** — the language, declared per-file via the `mklang:` field
  (currently `"0.2"`).
- **Package version** — the reference interpreter / tooling, SemVer in
  `pyproject.toml` (currently `0.2.0`).

## [Unreleased]

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

### Added

- **Formal `tool` states** — a state can invoke a host-registered callable so tool
  observations re-enter the context (real ReAct, not prose-simulated). Optional
  top-level `tools:` block; built-in demo tools (`calc`, `search`).
- **Cost accounting** — per-step token usage in the trace, a run total, and an
  optional `cost_budget` (halt `cost-exhausted`).
- **Error taxonomy** — `refusal` and `provider-error` halt reasons; typed adapter
  exceptions; `CallFailed` for sub-machine propagation.
- **Structured-output judge** — the OpenAI-compatible adapter judges via JSON mode
  with a regex fallback.
- Apache-2.0 `LICENSE`, `CONTRIBUTING.md`, this changelog.
- Quality: golden-trace and cookbook-conformance tests (the latter caught two
  invalid-YAML snippets in `SPEC.md §10`); Anthropic adapter unit tests
  (params/refusal/usage). Live Anthropic run deferred (no key available).
- Docs: SPEC header aligned to **0.2**; ROADMAP `[next]` items that already shipped
  marked done.

## [0.2.x] — hardening pass

### Added

- Per-tier `params` (effort / thinking / reasoning_effort) are now **applied** to the
  model, best-effort with drop-on-error.
- Pre-run validation in `mklang run`; richer `mklang check` (dead states,
  unproduced `result`, refined catch-all warning).
- Schema bundled as package data (works pip-installed); `mklang:` spec-version field;
  transient-error retry with backoff.

### Fixed

- Engine exception-safety (clean `halt`, isolated fan-out branches); empty-`eligible`
  no longer crashes; `--set` accepts JSON (lists for `over`); `load_registry` skips
  malformed siblings; `.env` discovered from cwd.

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
