"""Checkpoint frames and envelope I/O for resumable runs (ADR 0007)."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

FORMAT = 1


def _write_private(path: str | Path, text: str) -> None:
    """Write text with owner-only (0600) permissions.

    A checkpoint serializes the FULL blackboard — customer text, PII, internal
    policy — as plaintext JSON, and HITL suspends precisely on the most sensitive
    cases (escalations), so these files linger longest exactly when they matter
    most (SPEC §11). Encryption at rest is a host concern and an explicit v0.2
    non-goal; owner-only permissions are the cheap, real baseline. Create the file
    restricted from the start (no world-readable window) and chmod to cover a
    pre-existing file whose mode `os.open` would not tighten. POSIX-only: on
    Windows the mode is advisory and chmod may be a no-op."""
    p = Path(path)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chmod(p, 0o600)
    except (OSError, NotImplementedError):  # non-POSIX / unsupported filesystem
        pass


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
    }


def taint_frame(frame: dict, keys: Iterable[str]) -> None:
    """Mark host-injected top-level keys tainted in a checkpoint frame.

    Every `resume --set` / resume-inputs path must call this beside the ctx
    write: values crossing the host boundary are untrusted (ADR 0025)."""
    current = set(frame.get("tainted", frame.get("ctx", {}).keys()))
    current.update(k.split(".")[0] for k in keys)
    frame["tainted"] = sorted(current)


def file_sha256(path: str | Path) -> str | None:
    """None when `path` is not a file — a run-by-name machine (bundled stdlib)
    has no file to pin; its integrity is versioned with the package instead."""
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


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
) -> None:
    """`machine_source` carries the inline `.mkl` text for machines that have no
    file (MCP inline commissions), so a cross-process resume can rebuild them."""
    from . import __version__  # runtime import: __init__ imports engine imports this module

    envelope = {
        "format": FORMAT,
        "mklang_version": __version__,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
    _write_private(path, json.dumps(envelope, ensure_ascii=False, indent=2))


def load_checkpoint(path: str | Path) -> dict:
    ck = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(ck, dict) or ck.get("format") != FORMAT:
        raise ValueError(f"not an mklang checkpoint (expected format {FORMAT})")
    for key in ("machine", "machine_path", "machine_sha256", "frames"):
        if key not in ck:
            raise ValueError(f"checkpoint missing key {key!r}")
    if not ck["frames"]:
        raise ValueError("checkpoint has no frames")
    return ck


def verify_hash(ck: dict, machine_path: str | Path) -> bool:
    if ck["machine_sha256"] is None:  # run-by-name checkpoint: nothing to pin
        return True
    return bool(file_sha256(machine_path) == ck["machine_sha256"])
