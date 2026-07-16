# ADR 0004 — LLM as runtime; gates as the reliability mechanism

Status: Accepted

## Context

mklang could compile to a deterministic artifact (formal grammar, code) with the LLM
used only at authoring time. Instead we chose the LLM to _be_ the runtime: it
executes each state and (by judging `when` conditions) decides transitions. That
makes execution non-deterministic by construction. We need reliability without giving
up that premise.

## Decision

The LLM is the runtime. Reliability comes not from types but from **gates**:
natural-language post-conditions the model judges, each carrying a policy
(`ok`/`repair`/`escalate`/`fail`). Guardrails — global step `budget`, per-gate
`repair` budgets, call-depth cap, mandatory reachable `END` — bound divergence. The
**trace** makes every non-deterministic decision inspectable.

## Consequences

- The language is prose-first and writable by non-programmers for the common path;
  host code is optional (tools + code-hook gates) for exact checks and real I/O.
- Soft correctness rides on prompt/condition quality; critical checks should use
  code-hook gates (ADR 0006) plus authoring practices (docs/patterns.md).
- Determinism for critical gates is opt-in via **hooks**; caching remains later.
