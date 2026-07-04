# ADR 0002 — Fan-out reduces via an LLM state, not built-in aggregators

Status: Accepted

## Context

Fan-out (`sample`/`over`) produces a list of results. Something must collapse the
list to one value (self-consistency vote, map-reduce combine, debate synthesis). Two
options: built-in aggregator keywords (`aggregate: majority|best|concat`) on the
fan-out state, or an ordinary downstream state that reads the list and reduces it via
prompt + gates.

## Decision

**Reduction is an ordinary downstream state.** No built-in aggregators. The fan-out
state deposits a list; a normal generative state reads `{{list}}` and votes / selects
/ merges in prose.

## Consequences

- Keeps the model coherent: _everything_ is states + gates + prose. No second,
  non-LLM evaluation semantics to specify, validate, or teach.
- The schema stays simpler (no aggregator grammar).
- Reduction is non-deterministic (it's an LLM call) — acceptable, and consistent
  with the LLM-as-runtime premise (ADR 0004). A future code-hook gate (roadmap) can
  add deterministic reduction where needed without changing this default.
