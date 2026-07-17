# Contributing to mklang

Thanks for your interest. mklang is a small, opinionated project: a language spec
plus a reference interpreter. Keep changes coherent with the design in
[`SPEC.md`](./SPEC.md), the decisions in [`docs/adr/`](./docs/adr), and the
operating rules in [`docs/best-practices.md`](./docs/best-practices.md)
(especially **layer discipline**: language vs host tools vs surfaces).

## Dev setup

```bash
uv run --extra dev pytest -q          # unit + conformance (no network — MockLLM)
MKLANG_LIVE=1 uv run --extra dev pytest -q tests/test_live.py  # opt-in live smoke (active provider; MKLANG_LIVE_PROVIDER=… to override)
uv run --extra dev ruff check src tests
uv run mklang check examples/*.mk     # schema + semantic validation
uv run mklang lint --strict examples/*.mk   # + static analysis
uv run mklang test examples/triage.mk --script examples/triage.test.yaml  # scripted scenarios, no API keys
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
6. **Tests** — deterministic coverage with `MockLLM` in `tests/`; keep `ruff` clean.
7. **Docs** — `README.md`, `docs/patterns.md`, `CHANGELOG.md`, and `ROADMAP.md`.

A change to the **interpreter only** (no language change) skips steps 1–2 and 4
unless the host tooling surface needs a new conformance-facing scripted binding.

## Design decisions (ADRs)

Non-trivial or contentious decisions get a short ADR in `docs/adr/NNNN-title.md`
(Context / Decision / Consequences). See the existing ADRs in `docs/adr/`
(0001–0020) for the format. Reference the ADR in your PR.

## Versioning

- **Spec version** (`mklang:` field) changes when the _language_ changes.
- **Package version** (`pyproject.toml`, SemVer) changes when the _interpreter/tooling_
  changes. Record both in `CHANGELOG.md`.

## Releases

Releases are provenance-bound: update `pyproject.toml` and `mklang.__version__`
together, record the package release in `CHANGELOG.md`, and publish a GitHub
Release whose tag is exactly `v<package-version>`. The release workflow runs the
offline suite, strict docs/package checks, and the required live-provider gate;
only its previously tested artifacts reach PyPI through the protected `pypi`
environment and Trusted Publishing. Do not upload a locally rebuilt artifact for
an existing tag.

## Non-goals (don't propose these)

Pinning a concrete provider/model inside a `.mk` — machines route by capability tier
only (ADR 0003). See `SPEC.md §9` for the current non-goals.
