# Stability & versioning

What you can rely on, how mklang is versioned, and how breaking changes are made.
The normative version of this policy is
[ADR 0026](../adr/0026-stability-and-deprecation-policy.md); this page is the
user-facing summary. The language contract itself is [SPEC](../../SPEC.md).

## Two version lines

mklang carries two independent version numbers:

- **Spec version** — the _language_, declared per file via the `mklang:` field
  (currently `"0.3"`; `"0.2"` documents remain valid). It changes only when the
  language changes.
- **Package version** — the reference interpreter and tooling, SemVer in
  `pyproject.toml` (currently pre-1.0). It changes when the interpreter or
  tooling changes.

The two move independently: a package release often ships with the spec version
unchanged. Both lines are recorded in [CHANGELOG](../../CHANGELOG.md).

## What 1.0 promises

At 1.0.0 the **0.3 language surface is frozen** and the package adopts strict
SemVer:

- **MAJOR** — incompatible change to the stable surface.
- **MINOR** — additive, backward-compatible (new opt-in features, tooling, docs).
- **PATCH** — backward-compatible fixes.

The stable surface is the 0.3 language (machines, states, the four core faces
plus the optional faces, capability tiers, code-hook gates, the gate judge
protocol, and the trace shape — [SPEC §1–§8](../../SPEC.md)) together with the
documented host contracts (the `mklang.tools` / `mklang.hooks` /
`mklang.providers` / `mklang.machines` entry-point registries, the `run(...)`
embedding API, and the §6 untrusted-data delimiting). Pin a major version and
rely on no breaking **language** changes.

Explicitly **outside** the stable surface (free to change):

- The [SPEC §9](../../SPEC.md) non-goals — formal types, provider/model pinning,
  the `.mkl` extension, caching, dual-channel control.
- Host-side, non-normative behavior — CLI presentation, console UX, prompt
  assembly text, provider parameters.

## Deprecation cycle

A breaking change to the stable surface is never silent:

1. **Deprecate in a MINOR** — the old surface keeps working; the change is
   signalled by a CHANGELOG "Deprecated" entry, a `mklang check` / `lint` notice
   where statically detectable, and a runtime warning where observable.
2. **Remove no sooner than the next MAJOR**, and only after the deprecation has
   been documented for at least one full minor cycle.

Pre-1.0 behavior is not covered by this forward promise — the commitment runs
from 1.0.0 onward.

## Spec vs reference interpreter

[SPEC](../../SPEC.md) is the normative contract; `src/mklang/` is one conformant
reference implementation. A behavior change that is a valid reading of the 0.3
spec is a _package_ change (SemVer), not a spec change. A change that needs new
spec text is a _spec_ change (0.4+) and carries the conformance work the change
checklist requires.

## The `.mkl` extension

Machine files use the `.mkl` suffix (mklang), renamed from `.mk` to shed the
Makefile / Linguist collision
([ADR 0027](../adr/0027-adopt-mkl-extension.md)). The suffix is a discovery
convention, not part of the language contract: the document is YAML, and a
machine loads by explicit path regardless of suffix. Directory discovery
(`load_registry`, the CLI project scan) matches `*.mkl`.
