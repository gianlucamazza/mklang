# ADR 0033 — A state may bound its own re-entry

Status: Accepted (2026-08-08)

## Context

Loops are first-class in mklang: §7 names `repair`, loop-back gates and recursion as
the three ways non-determinism can diverge, and every guard the language ships is
global (`budget:`) or per-gate (`repair: N`). Nothing bounds _one state's_ share of a
run. The failure this leaves is specific and observed:

- A loop-back cycle that stops converging (`gather ↔ check_sufficiency`,
  `propose ↔ select`) eats the whole budget and dies as `budget-exhausted` — a cause
  that cannot distinguish "the machine was too ambitious" from "one cycle diverged",
  and does not name the cycle.
- The evidence row ADR 0031 requires: the platform's `D25`
  (mklang-platform `ops/TASKBOARD.md`) — a revise loop with no ceiling, where a
  machine that keeps escalating can cycle without limit and the only bound is that a
  human must answer each round. The platform cannot add the ceiling from outside the
  language: which state may repeat, and how often, is authored knowledge — exactly
  ADR 0031's condition 1, "flipping it needs information a `.mkl` cannot express".

A host-side run option was considered (the `MAX_CALL_DEPTH` precedent) and rejected:
the ceiling is per-state and belongs to the author of the machine, not to whoever
launches it; and a host option beside an authored field would be two mechanisms with
one meaning — the copy that diverges.

## Decision

1. **`max_visits: N`** — an optional integer (≥ 1) on any state face. The state may
   be entered at most N times per run; the (N+1)-th entry halts with **`loop-ceiling`**,
   `at` naming the state. Entries are counted at entry, before the state runs, so an
   entry the runtime aborts still counts — the same rule as `steps`.
2. **Guard order**: the ceiling is checked after the step and cost budgets, so an
   exhausted budget keeps its own name. `loop-ceiling` never suspends: a resumed run
   would re-enter the same over-visited state and halt again, so a checkpoint here
   would be a promise the machine cannot keep.
3. **Diagnosis**: on `budget-exhausted` / `cost-exhausted` the result carries an
   additive `diagnosis` (`most_visited_state`, `visits`) whenever some state was
   entered more than once — the question an author asks first, answered without
   reading the trace.
4. **Checkpoints**: per-state visit counts are run state and serialize into frames
   (`visits`, sorted keys). Frames that predate the field resume with the count
   reset — fail-open, because the ceiling is a divergence guard, not a security
   boundary, and failing closed would strand every existing checkpoint.
5. **This is spec 0.4** (new syntax; `stability.md` draws the line exactly there).
   0.3 documents remain valid; `check` warns when a 0.3 document uses the field and
   warns statically when a state's ceiling is at or under its own repair budget —
   a `loop-ceiling` guaranteed to fire mid-repair.

## Consequences

- The engine gains a `visits` counter (entry-counted, checkpointed); `_loop_guards`
  gains one check; conformance gains `loop-ceiling` and the budget-vs-ceiling
  ordering case.
- `budget-exhausted` stops being the opaque catch-all for divergence: authored
  ceilings turn it into a named, state-attributed halt; unauthored runs at least
  learn which state ate the budget.
- The platform can close `D25`'s language half by setting `max_visits` on the
  parking state of a revise loop; the workflow-level park ceiling remains the
  platform's own row.
- Not taken: a `while`/`until` construct (the FSM graph is the loop; a second
  spelling would be a divergent copy) and a formal `goal:` (§9 non-goal — the prose
  gate that routes to `END` is the success condition, and repair-convergence keeps
  it measured).
