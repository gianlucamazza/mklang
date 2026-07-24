# Contributing to mklang

Thanks for your interest. mklang is a small, opinionated project: a language spec
plus a reference interpreter. Keep changes coherent with the design in
[`SPEC.md`](./SPEC.md), the decisions in [`docs/adr/`](./docs/adr), and the
operating rules in [`docs/guides/best-practices.md`](./docs/guides/best-practices.md)
(especially **layer discipline**: language vs host tools vs surfaces).

## Dev setup

```bash
uv run --extra dev --extra mcp pytest -q --cov=mklang  # unit + conformance (no network — MockLLM); coverage gate ≥90% (needs --extra mcp: mcp/server.py counts toward the total)
MKLANG_LIVE=1 uv run --extra dev pytest -q tests/test_live.py  # opt-in live smoke (active provider; MKLANG_LIVE_PROVIDER=… to override)
uv run --extra dev ruff check src tests scripts
uv run --extra dev ruff format --check src tests scripts  # formatting (CI-gated); drop --check to fix
uv run --all-extras mypy              # static types (zero suppressions)
uv run mklang check examples/*.mkl     # schema + semantic validation
uv run mklang lint --strict examples/*.mkl   # + static analysis
uv run mklang test examples/triage.mkl --script examples/triage.test.yaml  # scripted scenarios, no API keys
```

`pytest` already runs the [conformance suite](./conformance/README.md)
(`tests/test_conformance.py` over `conformance/cases/*.yaml`). `mklang test` is
the same case format for **author-facing** scenario scripts next to a machine.

Secrets live in `.env` (gitignored); copy `.env.example` and add provider keys for
live runs. The example runtime defaults to **DeepSeek** (`DEEPSEEK_API_KEY` +
`active: deepseek`). Never commit a key.

### Plugin tools / hooks / providers

Third-party packages can register callables without patching core:

```toml
# in the plugin package's pyproject.toml
[project.entry-points."mklang.tools"]
my_search = "mypkg.tools:search"

[project.entry-points."mklang.hooks"]
amount_ok = "mypkg.hooks:amount_ok"

[project.entry-points."mklang.providers"]
my_vendor = "mypkg.providers:factory"  # (ProviderConfig) -> LLM
```

- Tools: `(dict) -> str` (tool-state observations).
- Hooks: `(context: dict, output) -> bool` (gate predicates).
- Providers: factory `(ProviderConfig) -> LLM`; unknown names fall back to the
  OpenAI-compatible adapter.

Entry-point plugins are host code and should be explicitly allowlisted in
production with `MKLANG_ALLOWED_PLUGINS=name1,name2`. An empty or unset value
keeps the development default of loading discovered plugins; a configured list
blocks every other plugin before it can register tools, hooks, or providers.
Tests for plugin policy and capability metadata belong in `tests/` and must not
depend on external credentials.

The CLI loads `load_tool_registry()` / `load_hook_registry()` / the provider
registry (builtins + entry points). Library users may still pass explicit
`tools=` / `hooks=` to `run()`.

## The change checklist

A change to the **language** must land as a coherent set — in this order:

1. **`SPEC.md`** — describe the behavior (the spec is the source of truth).
2. **`schema/mklang.schema.json`** — update the structural schema, then re-bundle the
   package copy: `cp schema/mklang.schema.json src/mklang/data/mklang.schema.json`
   (a test asserts the two stay identical).
3. **Interpreter** — `src/mklang/` (model, loader/validator, engine, adapters, CLI).
4. **Conformance** — if the change touches language semantics (SPEC §5–§7), add or
   update a case under `conformance/cases/` (ADR 0009).
5. **Examples** — add/adjust a machine in `examples/` that exercises the feature;
   where gate paths matter, a sibling `*.test.yaml` for `mklang test` is welcome.
6. **Tests** — deterministic coverage with `MockLLM` in `tests/`; keep `ruff`
   **and `mypy`** clean (zero suppressions) and coverage above the
   `fail_under = 90` gate.
7. **Docs** — `README.md`, `docs/guides/patterns.md`, `CHANGELOG.md`, and `ROADMAP.md`.

Keep `ruff format` clean too — the format check is CI-gated (`ruff format --check`),
not only `ruff check`.

A change to the **interpreter only** (no language change) skips steps 1–2 and 4
unless the host tooling surface needs a new conformance-facing scripted binding.

## Design decisions (ADRs)

Non-trivial or contentious decisions get a short ADR in `docs/adr/NNNN-title.md`
(Context / Decision / Consequences). See the [ADR index](./docs/adr/README.md)
for the format and the existing decisions. Reference the ADR in your PR.

## Versioning

- **Spec version** (`mklang:` field) changes when the _language_ changes.
- **Package version** (`pyproject.toml`, SemVer) changes when the _interpreter/tooling_
  changes. Record both in `CHANGELOG.md`.
- The full stability & deprecation policy (SemVer from 1.0.0, spec 0.3 frozen,
  the deprecation cycle) lives in
  [docs/guides/stability.md](./docs/guides/stability.md)
  ([ADR 0026](./docs/adr/0026-stability-and-deprecation-policy.md)).

## Releases

Releases are provenance-bound: update `pyproject.toml` and `mklang.__version__`
together, record the package release in `CHANGELOG.md`, and publish a GitHub
Release whose tag is exactly `v<package-version>`. The release workflow runs the
same reusable quality gate as CI (lint, mypy, coverage, the multi-platform
offline matrix) pinned to the tag, strict docs/package checks, and the required
live-provider gate;
only its previously tested artifacts reach PyPI through the protected `pypi`
environment and Trusted Publishing. Do not upload a locally rebuilt artifact for
an existing tag.

**Tag ↔ CHANGELOG invariant.** Every `CHANGELOG.md` entry from **0.5.3** upward
must carry a matching `v<version>` git tag; entries at or below **0.5.2** are
pre-distribution history and are exempt (the first PyPI release was 0.5.4). This
is enforced offline by `tests/test_release.py`
(`test_changelog_entries_from_distribution_cutoff_are_tagged`) — so a CHANGELOG
entry that was never released fails CI. Either tag it or drop it.

**Publish cadence.** A git tag is enough for a personal checkpoint; a **PyPI
publish is not free** — it is a durable, irreversible artifact others may depend
on. Publish to PyPI on a **user-visible change** (or a fixed interval, whichever
is slower), not on every internal checkpoint. Batch churn between real releases
behind local tags.

## Non-goals (don't propose these)

Pinning a concrete provider/model inside a `.mkl` — machines route by capability tier
only (ADR 0003). See `SPEC.md §9` for the current non-goals.
