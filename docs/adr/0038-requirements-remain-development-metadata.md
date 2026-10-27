# ADR 0038 — Requirements remain development metadata

Status: Accepted

## Context
Language conformance already has a canonical specification and implementation-neutral
cases. Cross-repository engineering must not move semantics into a private registry.

## Decision
Add stable LREQ identifiers mapped to existing cases and SPEC.md. The registry is
traceability metadata; SPEC.md and conformance remain authoritative. Use the engineering
v1 schema and pinned distribution of its offline validator in development CI only.
No runtime dependency, grammar, CLI, interpreter or conformance behavior changes.

## Consequences
A public clone remains independent. Mapping coverage is distinct from oracle quality.
New semantic cases require a new stable ID; existing IDs are never renumbered. A changed
case updates its requirement and invalidates old evidence. High-risk language changes
continue to need their own ADR and conformance case.
