# ADR 0007 — Resumable runs via loop-top checkpoints

Status: Accepted

## Context

A run that exhausts its step or token budget halts and loses all work. Pausing and
resuming (blackboard + position) is also the foundation for real human-in-the-loop:
an `escalate` that suspends and resumes on reply (ROADMAP). All run state lives as
locals of the `run()` loop in `engine.py`; the top of that loop — where the budget
checks already sit — is the one boundary with no in-flight LLM call and no partial
fan-out.

## Decision

- **Trigger (v1):** budget exhaustion (`budget-exhausted`, `cost-exhausted`)
  **suspends instead of halting** when the run is started with `suspendable=True`
  (CLI: `--checkpoint PATH` on `run`). Default off — a plain `run()` behaves as
  before. Suspension is a host-runtime behavior, not a language change: the spec
  version stays `0.2`.
- **Frames, not a rewritten loop:** the recursion of `call` is kept. A suspending
  sub-run raises an internal `_Suspend` carrying its loop-top **frame** (machine
  name, state, ctx, steps, token totals, feedback, repair budgets, trace); each
  parent `call` level prepends its own frame and re-raises; depth 0 returns
  `RunResult(status="suspended", frames=[root..innermost])`. A parent's totals never
  include a sub's partial spend (added only on call completion), so restoring
  per-frame totals reproduces the exact mid-flight budget chain.
- **Fan-out branches never suspend** (`suspendable=False` inside branches): a
  budget-exhausted sub inside a branch stays a `[branch-error: …]` marker; the
  spine suspends, if at all, at the next loop-top.
- **Envelope:** the CLI wraps frames in a JSON checkpoint file with `format: 1`,
  machine name + path + **sha256 of the root `.mkl`**, the suspend `reason`, and the
  cost budget. `mklang resume <checkpoint>` verifies the hash before any provider
  setup (`--force` to override, e.g. after deliberately raising `budget:`).
  `repair_left` tuple keys are encoded as `[state, gate_idx, remaining]` triples.
- **Exit codes:** 0 done, 1 halt, 2 load/check error, **3 suspended**.

## Consequences

- A run capped with `--max-tokens` can be continued with a larger budget instead of
  being thrown away; resuming with the same budget just re-suspends (idempotent).
- The resumed result (trace, usage, context, result) is identical to an
  uninterrupted run — verified by golden round-trip tests.
- The `reason` field is the forward hook for HITL: a suspending `escalate` writes
  `reason: "escalated"` into the same envelope with no format change.
- Limitation: only the root `.mkl` is hashed; sub-machines are verified by name
  against the reloaded registry, so silent drift in a sub-machine file is not
  detected in v1.
