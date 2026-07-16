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

- The language is prose-first for the common path; the host still supplies the
  interpreter, and production machines need tools + code-hook gates for exact
  checks and real I/O.
- Soft correctness rides on prompt/condition quality; critical checks should use
  code-hook gates (ADR 0006) plus authoring practices (docs/patterns.md).
- Determinism for critical gates is opt-in via **hooks**; caching remains later.
- **"Reliability comes from gates" is an empirical claim.** Prose gates are judged
  by the same class of model whose unreliability they contain. Repair budgets,
  hooks, and escalate mitigate this; they do not erase it. There is no published
  judge-accuracy or cross-provider gate-agreement measurement in-tree yet — the
  conformance suite pins _interpreter_ rules with a scripted LLM, not judge
  reliability. Treat semantic portability across providers as measured, not free
  (see `scripts/gate_divergence.py` / docs/experiments).
