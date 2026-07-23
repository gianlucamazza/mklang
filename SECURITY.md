# Security policy

## Supported versions

mklang is pre-1.0: only the **latest released package version** receives
security fixes. The language spec version (`mklang:` per-file field) is
independent — see [CHANGELOG.md](./CHANGELOG.md) for the two version lines.

## Reporting a vulnerability

Please report vulnerabilities **privately** via
[GitHub Security Advisories](https://github.com/gianlucamazza/mklang/security/advisories/new)
— do not open a public issue. Expect an acknowledgement within a week.

In scope:

- The reference interpreter (`src/mklang/`): engine, adapters, CLI, MCP
  server, console, host tools (fs workspace confinement, write grants).
- The delimiting guarantees of SPEC §6 (a way to make untrusted content
  escape its `<data-NONCE>` fence, forge a closing tag, or launder taint).
- Checkpoint handling (0600 files, resume taint fail-safe).

Out of scope (documented limitations, not vulnerabilities):

- Model _persuasion_ by fenced content — SPEC §11 states delimiting is a
  mitigation, not a proof; dual-channel control is an open question (§9).
- Checkpoint-at-rest confidentiality beyond file permissions (host-side
  concern, SPEC §11).
- Provider/API-key compromise and network policy (host-side).

## Threat model

The language's honest threat model lives in [SPEC.md §11](./SPEC.md) —
assets, trust boundary, known attack surface, and partial mitigations.
Design decisions are recorded in [docs/adr/](./docs/adr/), notably
[ADR 0025](./docs/adr/0025-untrusted-context-delimiting.md) (untrusted-context
delimiting) and [ADR 0024](./docs/adr/0024-fs-data-tools.md) (fs workspace
model).
