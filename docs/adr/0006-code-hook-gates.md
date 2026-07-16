# ADR 0006 — Code-hook gates alongside LLM-judged gates

Status: Accepted

## Context

Gates are the reliability mechanism (ADR 0004). Natural-language `when` conditions
are flexible but non-deterministic: exact checks (`amount <= 100`,
`total == sum(lines)`) cannot be trusted to an LLM alone. Production pipelines need
**deterministic layers** independent of the judge (best practice: fail-closed exact
checks next to probabilistic judgement).

## Decision

A gate MAY carry an optional **`hook: <name>`**. The host registers
`name → callable(context, output) -> bool`. Evaluation (top to bottom):

1. **Hook gate** — invoke the callable; if `True`, the gate fires (no LLM).
2. **`when: otherwise`** — always true when reached (no LLM, hook ignored).
3. **Prose gate** — consecutive prose-only gates are fused into one `LLM.judge`
   call (existing behaviour); the first true among that batch fires.

Optional top-level `hooks:` declarations document expected names (like `tools:`).
The binding stays host-side (`run(..., hooks=...)`; CLI ships demo builtins).

`when` remains required on every gate as the **trace label** and documentation of
intent — even when a hook does the actual test.

## Consequences

- Critical policies can mix exact host checks with LLM soft judgement in one table.
- Machines that declare `hooks:` stay portable; hosts that do not bind a name halt
  with a clear error if that gate is reached.
- Formal types for `structure` remain a separate non-goal; hooks cover the
  highest-ROI deterministic slice without a type system.
