"""Checkpoint frames and envelope I/O for resumable runs (ADR 0007)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FORMAT = 1


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
    }


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_checkpoint(
    path: str | Path,
    machine_name: str,
    machine_path: str | Path,
    reason: str,
    frames: list[dict],
    cost_budget: int | None,
) -> None:
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
        "frames": frames,
    }
    Path(path).write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")


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
    return file_sha256(machine_path) == ck["machine_sha256"]
