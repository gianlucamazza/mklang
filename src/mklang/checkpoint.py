"""Checkpoint frames and envelope I/O for resumable runs (ADR 0007).

Where a checkpoint *goes* is a host decision (ADR 0032). This module owns the envelope —
`FORMAT`, the JSON encoding, `machine_sha256` — and hands a store bytes, because a store
that received a dict would have to know the format in order to serialize it, and
encryption would end up in here. Bytes is the narrowest thing that lets a host encrypt
without this repository knowing that it did.

`FileCheckpointStore` is the default and is where `_write_private()`'s `0600` semantics
live. With no store supplied, `save_checkpoint` and `load_checkpoint` behave exactly as
they always have.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

FORMAT = 1


def _write_private(path: str | Path, text: str) -> None:
    """Write text with owner-only (0600) permissions.

    A checkpoint serializes the FULL blackboard — customer text, PII, internal
    policy — as plaintext JSON, and HITL suspends precisely on the most sensitive
    cases (escalations), so these files linger longest exactly when they matter
    most (SPEC §11). Encryption at rest is a host concern and there is now a seam
    for it — `CheckpointStore`, ADR 0032 — so this stays the honest baseline for
    the default store rather than a disclaimer. Create the file
    restricted from the start (no world-readable window) and chmod to cover a
    pre-existing file whose mode `os.open` would not tighten. POSIX-only: on
    Windows the mode is advisory and chmod may be a no-op."""
    p = Path(path)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    # non-POSIX / unsupported filesystem: mode is advisory
    with contextlib.suppress(OSError, NotImplementedError):
        os.chmod(p, 0o600)


def encode_repair(repair_left: dict[tuple[str, int], int]) -> list[list]:
    """Tuple-keyed repair budgets → JSON-safe [state_id, gate_idx, remaining] triples."""
    return [[sid, gi, n] for (sid, gi), n in repair_left.items()]


def decode_repair(triples: list) -> dict[tuple[str, int], int]:
    return {(sid, gi): n for sid, gi, n in triples}


def make_frame(
    machine_name: str,
    state_id: str,
    ctx: dict,
    steps: int,
    total_in: int,
    total_out: int,
    feedback: str,
    repair_left: dict[tuple[str, int], int],
    trace: list[dict],
    tainted: set[str] | None = None,
    external: set[str] | None = None,
    flow_tainted: bool = True,
    visits: dict[str, int] | None = None,
) -> dict:
    """Snapshot one run() loop-top: everything needed to re-enter the loop."""
    return {
        "machine": machine_name,
        "state": state_id,
        "ctx": dict(ctx),
        "steps": steps,
        "total_in": total_in,
        "total_out": total_out,
        "feedback": feedback,
        "repair_left": encode_repair(repair_left),
        "trace": list(trace),
        # Provenance taint (ADR 0025). Resume treats a missing field as
        # all-tainted, so pre-0025 checkpoints stay resumable and fail safe.
        "tainted": sorted(tainted or ()),
        # Control-flow taint (ADR 0030): the external subset of `tainted`, and
        # whether the decision that reached this state was judged over external
        # data. Both default to the unsafe side on a frame that lacks them.
        "external": sorted(external if external is not None else (tainted or ())),
        "flow_tainted": bool(flow_tainted),
        # Per-state entry counts for `max_visits` (SPEC §7). Sorted so identical
        # run state yields identical bytes (the suspend path is idempotent).
        # Frames without the field resume with the count reset — fail-open,
        # stated in `_from_resume`.
        "visits": {k: int((visits or {})[k]) for k in sorted(visits or {})},
    }


def taint_frame(frame: dict, keys: Iterable[str]) -> None:
    """Mark host-injected top-level keys tainted in a checkpoint frame.

    Every `resume --set` / resume-inputs path must call this beside the ctx
    write: values crossing the host boundary are untrusted (ADR 0025) and, having
    come from outside the run, external for control-flow purposes (ADR 0030)."""
    paths = [str(k) for k in keys]
    injected = {k.split(".")[0] for k in paths}
    current = set(frame.get("tainted", frame.get("ctx", {}).keys()))
    frame["tainted"] = sorted(current | injected)
    external = set(frame.get("external", frame.get("tainted", frame.get("ctx", {}).keys())))
    frame["external"] = sorted(external | injected)
    # What THIS resume injected (ADR 0030). Overwritten, never merged, and absent
    # from a freshly made frame: a human reply confirms the suspension it was
    # given for, not every later one it happens to still be sitting in.
    frame["resume_injected"] = sorted(paths)


def file_sha256(path: str | Path) -> str | None:
    """None when `path` is not a file — a run-by-name machine (bundled stdlib)
    has no file to pin; its integrity is versioned with the package instead."""
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


class CheckpointStore(Protocol):
    """Where a checkpoint's bytes live (ADR 0032).

    Two methods, deliberately. It is a seam that makes substitution mechanical, not a
    storage abstraction; a third method should be asked for by a second real
    implementation rather than anticipated.
    """

    def put(self, data: bytes, *, key: str) -> str:
        """Store `data` and return the location it can be fetched back from.

        `key` is a naming hint, not an identity: a store may use it, ignore it, or hash
        it. The location is opaque to mklang, which never parses it, never joins it to
        anything, and never assumes it is a path — that is what lets a host hold a
        reference rather than a filename.
        """
        ...

    def get(self, location: str) -> bytes: ...


class FileCheckpointStore:
    """The default: a file per checkpoint, owner-only.

    A checkpoint serializes the FULL blackboard — customer text, PII, internal policy —
    as plaintext JSON, and HITL suspends precisely on the most sensitive cases, so these
    files linger longest exactly when they matter most (SPEC §11). Encryption at rest is
    a host concern; this store is the honest baseline and `0600` is a floor, not
    encryption. A host that must do better supplies its own store, which is what ADR 0032
    exists for.
    """

    def put(self, data: bytes, *, key: str) -> str:
        _write_private(key, data.decode("utf-8"))
        return str(key)

    def get(self, location: str) -> bytes:
        return Path(location).read_bytes()


def encode_checkpoint(
    machine_name: str,
    machine_path: str | Path,
    reason: str,
    frames: list[dict],
    cost_budget: int | None,
    hitl: bool = False,
    machine_source: str | None = None,
    metadata: dict | None = None,
) -> bytes:
    """The envelope, as bytes. What a store is handed, and what mklang keeps owning."""
    from . import __version__  # runtime import: __init__ imports engine imports this module

    envelope = {
        "format": FORMAT,
        "mklang_version": __version__,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "machine": machine_name,
        "machine_path": str(machine_path),
        "machine_sha256": file_sha256(machine_path),
        "reason": reason,
        "cost_budget": cost_budget,
        "hitl": hitl,
        "frames": frames,
    }
    if machine_source is not None:
        envelope["machine_source"] = machine_source
    if metadata:
        # Metadata is host policy/provenance only; callers must redact secrets
        # before passing it here. Keep it additive for old checkpoint readers.
        envelope["metadata"] = dict(metadata)
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def save_checkpoint(
    path: str | Path,
    machine_name: str,
    machine_path: str | Path,
    reason: str,
    frames: list[dict],
    cost_budget: int | None,
    hitl: bool = False,
    machine_source: str | None = None,
    metadata: dict | None = None,
    store: CheckpointStore | None = None,
) -> str:
    """`machine_source` carries the inline `.mkl` text for machines that have no
    file (MCP inline commissions), so a cross-process resume can rebuild them.

    Returns the location the store wrote to — the path itself for the default file
    store, which is what every existing caller already knew and none of them read.
    """
    data = encode_checkpoint(
        machine_name,
        machine_path,
        reason,
        frames,
        cost_budget,
        hitl=hitl,
        machine_source=machine_source,
        metadata=metadata,
    )
    return (store or FileCheckpointStore()).put(data, key=str(path))


def decode_checkpoint(data: bytes) -> dict:
    ck = json.loads(data.decode("utf-8"))
    if not isinstance(ck, dict) or ck.get("format") != FORMAT:
        raise ValueError(f"not an mklang checkpoint (expected format {FORMAT})")
    for key in ("machine", "machine_path", "machine_sha256", "frames"):
        if key not in ck:
            raise ValueError(f"checkpoint missing key {key!r}")
    if not ck["frames"]:
        raise ValueError("checkpoint has no frames")
    return ck


def load_checkpoint(path: str | Path, store: CheckpointStore | None = None) -> dict:
    return decode_checkpoint((store or FileCheckpointStore()).get(str(path)))


def verify_hash(ck: dict, machine_path: str | Path) -> bool:
    if ck["machine_sha256"] is None:  # run-by-name checkpoint: nothing to pin
        return True
    return bool(file_sha256(machine_path) == ck["machine_sha256"])
