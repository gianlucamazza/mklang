# ADR 0001 — Capability tiers, not model names

Status: Accepted

## Context

States differ in how much model capability they need: a classifier is cheap, a
final synthesis is not. We must let authors express that without naming models
(which would couple a `.mkl` to one provider — see ADR 0003).

## Decision

States route by a **provider-neutral capability tier** — `fast` / `balanced` /
`reasoning` — set per machine (`default_tier`) and overridable per state (`tier`).
The runtime holds a `tier → (provider, model)` map in its config. A tier applies to
both generation and gate-judging. The reference interpreter is **tier-following by
default** (a `reasoning` state's gates are judged by the reasoning model); a runtime
MAY use a cheaper model for judging as an optimization, exposed here as the opt-in
`judge:` config override — never the silent default (see the 0.5.2 remediation).

## Consequences

- The same `.mkl` runs on any backend by swapping the config's tier map.
- Cost control is a first-class, readable property of the machine (see the
  speculative-cascade pattern).
- The tier vocabulary is deliberately small (three levels); finer control lives in
  the runtime config `params`, not the `.mkl`.
