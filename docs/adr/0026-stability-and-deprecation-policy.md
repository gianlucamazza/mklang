# ADR 0026 — Stability & deprecation policy for the package and the spec version

Status: Accepted

## Context

mklang carries **two independent version lines** (CONTRIBUTING "Versioning",
CHANGELOG):

- **Spec version** — the language, declared per-file via the `mklang:` field
  (currently `"0.3"`; `"0.2"` documents remain valid).
- **Package version** — the reference interpreter / tooling, SemVer in
  `pyproject.toml` (currently `0.16.0`, pre-1.0).

Through 0.13–0.16 the project shifted from feature growth to **maturity**: CI
quality gates (mypy zero-suppressions, coverage ratchet, multi-platform matrix),
untrusted-context delimiting (ADR 0025), packaging/hygiene, and a four-machine
gate-divergence suite at agreement 1.0. The language itself (spec 0.3) has been
unchanged since 0.6.0. The one remaining item the maturity assessment named as a
blocker is a **stated stability commitment** — what users can rely on, and how
breaking changes are made. Without it, "1.0" is just a number.

## Decision

### 1. Package versioning — SemVer from 1.0.0

- **Pre-1.0 (0.x):** a MINOR bump may include breaking changes; this is the
  conventional 0.x freedom the project has used.
- **From 1.0.0:** strict SemVer. **MAJOR** = incompatible change to the stable
  surface; **MINOR** = additive, backward-compatible (new opt-in features,
  tooling, docs); **PATCH** = backward-compatible fixes. The spec version is
  independent and may stay constant across many package releases (§3 below).

### 2. Spec versioning — 0.3 is frozen as the 1.0 language surface

- **Spec 0.3 is frozen.** It is the language contract at 1.0; the §9 non-goals
  enumerate what sits outside it.
- The package may advance (additive features, interpreter/tooling) **without**
  bumping the spec, as long as (a) `mklang: "0.3"` documents remain valid and
  (b) behavior is a conformant reading of the 0.3 spec. A spec bump (0.4+) is a
  deliberate release of its own, gated by the conformance suite (ADR 0009).

### 3. The stable surface at 1.0

Users may rely on, at 1.0.0:

- The **0.3 language**: machines, states, the four core faces
  (`structure`/`prompt`/`execution`/`gates`) plus the optional faces
  (`reason`, `accumulate`, fan-out `sample`/`over`, `call`, `tool`, `parse:
  list`), capability tiers, code-hook gates, the gate evaluation order and judge
  protocol (§5), and the trace shape (§8).
- The **documented host contracts**: the `mklang.tools` / `mklang.hooks` /
  `mklang.providers` / `mklang.machines` entry-point registries, the `run(...)`
  embedding API, and the §6 untrusted-data delimiting (ADR 0025).

Explicitly **outside** the stable surface: every item in SPEC §9 (formal types,
provider/model pinning, the `.mkl` extension, caching, dual-channel control) and
all host-side, non-normative behavior (CLI presentation, console UX, prompt
assembly text, provider params) — these may change freely.

### 4. Deprecation cycle for future breaking changes

A breaking change to the stable surface follows a deprecation cycle, never a
silent removal:

1. **Deprecate in a MINOR.** The old surface stays functional; the change is
   signalled by a `CHANGELOG.md` "Deprecated" entry, a `mklang check` / `lint`
   notice where statically detectable, and a runtime warning where the behavior
   is observable at run time.
2. **Remove no sooner than the next MAJOR**, and only after the deprecation has
   been documented for at least one full minor cycle.
3. The conformance suite (ADR 0009) and `tests/test_release.py` stay the
   mechanical proof that the surface moves as one.

Pre-1.0 behavior is **not** covered by this forward promise — the stability
commitment runs from 1.0.0 onward.

### 5. Spec is the contract; the reference interpreter is one implementation

SPEC.md is the normative contract; `src/mklang/` is a conformant reference
implementation, not the contract itself. A behavior change that is a valid
reading of the 0.3 spec is a **package** change (SemVer), not a spec change. A
behavior change that requires new spec text is a **spec** change (0.4+) and
carries the conformance work the change checklist requires.

## Consequences

- Users can pin a major version and rely on no breaking **language** changes;
  host-side defaults may still shift within the documented non-normative surface.
- At 1.0.0 the classifier moves `Development Status :: 4 - Beta` →
  `5 - Production/Stable`, and `SECURITY.md`'s "pre-1.0" line updates to the
  supported-versions policy stated here.
- The frozen surface is enumerable from SPEC §1–§8; §9 lists the exclusions.
  Anything not in either list is non-normative host behavior.
- The user-facing explanation lives in
  [docs/guides/stability.md](../guides/stability.md).
