# ADR 0009 — Conformance suite as the language contract

Status: Accepted

## Context

Until now "mklang" and "the reference interpreter" were the same artifact: every
test exercised `mklang.engine`, so the language had no existence independent of
this Python implementation. A language needs a contract a second implementation
can be held to.

## Decision

- **`conformance/cases/*.yaml`** — implementation-neutral cases: an inline
  machine, a fully scripted LLM (sequential or prompt-keyed produce, indexed
  judge picks, fixed token costs), and the expected outcome (status, halt
  reason, result, context keys, and a _skeleton_ trace match).
- The **scripted-LLM contract** is part of the suite (documented in
  `conformance/README.md`): given the same case, any conforming interpreter
  must produce the same status/route/halt reason. Trace matching is a subset
  check so implementations remain free to add annotation keys.
- **Scope = the language** (SPEC §5–§7): gate policies, `otherwise`, fused
  judging, repair budgets, step/cost budgets, `call` and its failure
  propagation, fan-out, `accumulate`, result selection, halt taxonomy.
  Host behavior stays out: checkpoints/HITL (ADR 0007/0008), `tool`/`hook`
  bindings, provider adapters.
- The reference runner (`tests/test_conformance.py`) binds the suite to this
  interpreter in CI; a new implementation ships its own runner over the same
  YAML files.

## Consequences

- Semantics are pinned by executable cases, not only prose: a SPEC change now
  requires a case change, and regressions in the engine surface as conformance
  failures, distinct from unit-test failures.
- Writing a second interpreter (TypeScript, Rust, …) becomes a bounded task:
  parse YAML machines, satisfy the scripted-LLM contract, pass the cases.
- The suite grows with the language: every new semantic (a future typed
  `structure`, determinism knobs) must land with cases before it counts as
  part of mklang.
