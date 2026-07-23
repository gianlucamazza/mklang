# ADR 0027 — Adopt the `.mkl` extension (rename from `.mk`)

Status: Accepted

## Context

mklang's machine files used the `.mk` suffix (mk = _machine_). It shared its
suffix with Makefile **include** fragments, so tooling mislabelled it: GitHub
Linguist classifies `.mk` as Makefile, and editors apply Make highlighting. This
was long an open packaging question (SPEC §9), with a prior lean toward retaining
`.mk` because the collision is cosmetic — a stray `.mk` is not run as a Makefile
unless a `Makefile` includes it, so the practical risk is highlighting
misclassification, not mis-execution.

Two facts made a rename cheap **now**:

- The suffix is a **discovery convention**, not a language contract. The document
  is a YAML mapping (SPEC §3); the loader parses it as YAML by explicit path
  regardless of suffix. Only _directory_ discovery keys on the suffix — the
  registry globs `*.mkl` (`src/mklang/registry.py`) and the CLI scans a project
  directory for `*.mkl`. A single machine loaded by path needs no particular
  suffix.
- The rename cost grows with adoption. Pre-1.0, with effectively no external
  `.mk` machines in the wild, the cost is at its minimum; after a stable 1.0 it
  would be a breaking change requiring a deprecation cycle (ADR 0026).

## Decision

**Rename `.mk` → `.mkl` (mklang), hard cut.** Every machine file, the registry
discovery globs, the CLI project scan, the console `write_machine`, the bundled
machines, examples, tests, packaging, and docs move to `.mkl` together. Discovery
matches `*.mkl` only — there is no dual-suffix transition, because the rename
ships with 1.0 and there is no stable `.mk` user base to deprecate.

The Linguist misclassification is fixed structurally (`.mkl` is not a Makefile
suffix) and reinforced by a `.gitattributes` override
(`*.mkl linguist-language=YAML`) so GitHub highlights machines as YAML.

## Consequences

- One consistent `.mkl` suffix across the project; the Makefile / Linguist
  collision is gone.
- `.mk` machines remain loadable by **explicit path** (the loader parses YAML
  regardless of suffix), but they are no longer auto-discovered by directory — a
  project's machines must use `.mkl` to be picked up by `load_registry` and the
  CLI project scan. This is the one user-visible breaking edge of the rename.
- The suffix stays a convention: the spec is agnostic to it, and any future
  further rename would again touch discovery only, not semantics.
- SPEC §9 closes the extension item; the rename is recorded under CHANGELOG
  `[Unreleased]`.
