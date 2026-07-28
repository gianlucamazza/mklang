# ADR 0031 — What would force a language 0.4

Status: Accepted

## Context

ADR 0026 freezes the language at **0.3** and commits SemVer for the package.
ADR 0028 keeps package 1.0 and marks the freeze **“provisional on evidence”** —
then names conditions for a package **2.0** only. The spec line has one bullet
("spec debt: a conformance-gated 0.4+ release that cannot remain a pure superset")
which says what a 0.4 would *cost*, not what would *cause* one.

So "provisional on evidence" currently has no falsifier. A freeze whose exit
condition is unwritten is not provisional; it is permanent with a friendly label,
because every specific proposal can be deferred on the general principle that the
surface is frozen — and nothing ever accumulates into a decision.

The honest moment to write the criteria is now, while there is no pressure. Two
of the four candidates below became concrete this week (ADR 0030's `report`
default, SPEC §5 totality), which is exactly when the temptation to write
self-serving criteria is lowest: the answers are not yet known.

## Decision

A language **0.4** is warranted when **any** condition below is met. Each is
falsifiable, has a named measurement, and can be checked without a judgement
call about "elegance".

### 1. A normative rule cannot be enforced without new syntax

**Trigger.** A rule normative in SPEC §5/§6/§7 has a default that the evidence
says is wrong, and flipping it needs information a `.mkl` cannot express.

**Live instance.** ADR 0030 defaults `on_untrusted_flow` to `report`. Flipping
the default to `halt` is a language decision, not a host one, and doing it well
needs per-state effect declarations (an `effects:` face) or per-gate
confirmation (`hitl:`), neither of which exists in 0.3. **Measurement:** across
the machines in `examples/` + `src/mklang/data/` and any external machines
recorded in `docs/experiments/`, if **more than one in four** effectful tool
states is reachable on a tainted decision (`mklang lint` note count / total
effectful tool states) *and* authors report the read-only/effectful registry
split is too coarse, that is the trigger. Below that threshold, the host policy
plus the lint note is enough.

### 2. A totality or determinism hole needs a syntactic fix

**Trigger.** SPEC §5 "Totality and determinism" holds only when a state has an
eligible non-`repair` catch-all, and today that is a lint finding, not a
constraint. If measurement shows authors ship partial transitions anyway —
**more than 10%** of states in machines outside this repo lacking a catch-all,
or any `no-gate-matched` halt reported from a machine that passed
`lint --strict` — then the schema should require it (a breaking schema change,
hence 0.4).

**Not a trigger:** the reference interpreter changing *how* it reaches the same
transition (the 0.4-candidate fusion strategy, batching, caching). Those are
host behaviour under a fixed rule.

### 3. A measured reliability claim fails and the fix is in the language

**Trigger.** One of the standing experiments returns a result that a host-side
change cannot address:

- **Repair does not converge.** `docs/experiments/repair-convergence.md` reports
  `lift ≤ 0` on ≥3 machines over ≥50 runs on ≥2 providers. Then `repair(N)`'s
  feedback contract is wrong as specified — the honest fix is a language one
  (make the feedback channel explicit, or rename the construct to what it does).
- **Paraphrase invariance is low.** `paraphrase_invariance_rate < 0.8` on the
  boundary corpus over ≥2 providers means prose conditions are not a stable
  interface, and the language must offer authors something more than free text
  for consequential gates (a structured predicate face beside `hook:`).
- **Judge accuracy is far below agreement.** `gate_blind_spot > 0.25` sustained
  across dated runs means the reliability story rests on consensus rather than
  correctness, and gates need a construct that does not depend on a judge.

### 4. External use produces a contract-shaped defect

**Trigger.** An external user (not the author) files a defect that cannot be
fixed in the host, the docs, or a new stdlib machine — i.e. the fix requires
changing what a `.mkl` may say. **One** such report is enough: at the current
external-exercise level (ADR 0028 §4: none), the first real one is worth more
than any amount of internal reasoning.

## Non-triggers (explicit)

To keep the criteria honest, these do **not** justify a 0.4, however tempting:

- A cleaner spelling for something already expressible.
- A construct another framework has (graphs, typed signatures, optimizers) with
  no defect of ours attached to it.
- Author convenience that a stdlib machine or a host tool can deliver.
- The reference interpreter wanting a new trace field or annotation — §8 already
  lets hosts add annotation keys.

## How a 0.4 ships when triggered

Per ADR 0026 and the stability guide: a spec bump is its own release, gated by
the conformance suite, and the 0.3 surface stays a **pure superset** unless the
trigger itself is the thing that cannot remain compatible (condition 2 is the
only one that plausibly cannot). The triggering evidence — the dated experiment
row or the external report — is cited in the ADR that proposes the bump. No 0.4
proposal without a citation.

## Consequences

- Positive: "provisional on evidence" (ADR 0028 §5) now has an actual
  falsifier, and each candidate names the file where the number will appear.
- Positive: the pending decisions this week (ADR 0030's default, §5 totality
  enforcement) have a written path from "host policy" to "language rule" instead
  of drifting.
- Negative: thresholds (1 in 4, 10%, 0.8, 0.25, ≥50 runs) are judgement calls
  made before the data. They are deliberately specific so that missing them is
  visible; revising one requires an ADR amendment citing the run that motivated
  it — never a quiet edit while looking at the result.
- Negative: three of four conditions depend on experiments with **no live rows
  yet**. Until those exist, the criteria are a commitment, not a verdict.
