# ADR 0032 — A pluggable checkpoint store

Status: Accepted

## Context

ADR 0007 gave runs a checkpoint envelope and ADR 0008 made suspending routine, so
checkpoints are now ordinary artifacts of normal operation rather than an edge case.
`checkpoint.py` writes them to a filesystem path with owner-only permissions, and its
own docstring states the limit precisely:

> A checkpoint serializes the FULL blackboard — customer text, PII, internal policy —
> as plaintext JSON, and HITL suspends precisely on the most sensitive cases
> (escalations), so these files linger longest exactly when they matter most (SPEC
> §11). Encryption at rest is a host concern and an explicit v0.2 non-goal.

Both halves of that are right. The problem is that the second half is not currently
actionable: encryption at rest is a host concern, but there is no seam through which a
host can supply it. `save_checkpoint(path, …)` and `load_checkpoint(path)` take a
filesystem path, `_write_private()` opens it at `0600`, and the only thing a host can
choose is which path. A host that must encrypt has to write the file first and then
encrypt it in place, which is the plaintext window it was trying to avoid.

Two forces make this concrete now rather than theoretical.

**A host with a real requirement.** `mklang-platform` ADR 0006 requires checkpoints
encrypted at rest under a per-tenant key, in a store the platform owns, addressed by a
reference rather than by a path. Its ADR 0010 says a change to this repository driven
by platform needs requires an ADR _here_ rather than a quiet patch — this is that ADR.

**Cross-process resume already exists.** ADR 0013 named durable resume on the MCP
surface, and a host that commissions machines from more than one process needs both
processes to reach the same checkpoint. A filesystem path assumes a shared filesystem,
which is an assumption the language never meant to make.

`save_checkpoint` and `load_checkpoint` are exported in `__init__.__all__`. Under ADR
0026 that makes this additive or nothing.

## Decision

Introduce a store protocol, and change nothing else.

```python
class CheckpointStore(Protocol):
    def put(self, data: bytes, *, key: str) -> str: ...
    def get(self, location: str) -> bytes: ...
```

**The store moves bytes, not envelopes.** mklang keeps owning the envelope format —
`FORMAT`, the JSON encoding, the frame layout, `machine_sha256`. A store that received a
dict would have to know the format in order to serialize it, and encryption would end up
inside this repository. Bytes is the narrowest thing that lets a host encrypt without
mklang knowing that it did.

**`put` returns a location, opaque here and meaningful to the store.** The file store
returns the path it wrote. A platform store returns whatever it can resolve later.
mklang never parses a location, never joins it to anything, and never assumes it is a
path — that is what lets a host hold a reference rather than a filename.

**`key` is a naming hint, not an identity.** Callers pass something descriptive — the
console already builds `turn-%H%M%S-%f.json` at `console/app.py:682` — and a store may
use it, ignore it, or hash it. Identity is the location the store hands back.

**`FileCheckpointStore` is the default**, and is where `_write_private()`'s `0600`
semantics move. With no store supplied, behaviour is exactly what it is today.

**`save_checkpoint` and `load_checkpoint` keep their signatures** and become thin calls
over the file store. All seven existing call sites — `cli.py`, `mcp/server.py`,
`console/app.py` — are untouched.

**Choosing a store is a host decision, not a language one.** No `.mkl` mentions it, no
`.mkl` behaves differently because of it, and the spec version does not move. This is the
same posture ADR 0007 took: suspension is a host-runtime behaviour, not a language
change.

### Not in scope

- **Encryption.** This repository gains no crypto dependency and no concept of a key. A
  store that encrypts is a host's store, and that is the whole point of the seam.
- **Listing, expiry, and garbage collection.** The console lists parked checkpoints by
  globbing a directory (`console/app.py:552`). Promoting that to a protocol method would
  grow the interface to fit one caller and one implementation. It stays file-store
  behaviour until a second store actually needs it.
- **Machine-file integrity.** `file_sha256()` and `verify_hash()` pin the `.mkl`, not the
  checkpoint. They stay filesystem-facing and unchanged.

## Consequences

- A host can put checkpoints where its own security model requires — encrypted, in a
  database, in object storage — without this repository knowing any of it. That is what
  "encryption at rest is a host concern" has to mean in order to be a boundary rather
  than a disclaimer.
- Cross-process resume stops assuming a shared filesystem.
- The public surface grows by one protocol and one class, with no signature change and
  no deprecation. Additive under ADR 0026, so no spec bump and no package major.
- Two methods is the whole interface, deliberately. It is a seam that makes substitution
  mechanical, not a storage abstraction; if it grows a third method, the reason should be
  a second real implementation asking for it, not a hypothetical one.
- The cost is two ways to say the same thing: `save_checkpoint(path, …)` and
  `store.put(…)`. Removing the first would break the public surface for no gain, so both
  stay and the file store is the bridge.
- **The console's checkpoint listing stays file-specific.** A host on a non-file store
  gets no `/checkpoints` listing there until someone decides what listing means for a
  store in general. Recorded here so it is a known gap rather than a later surprise.
