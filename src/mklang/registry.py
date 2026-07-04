"""Machine registry: load every .mk in a directory, keyed by `machine:` name."""

from __future__ import annotations

from pathlib import Path

from .loader import load_machine
from .model import Machine


def load_registry(directory: str | Path, validate: bool = True) -> dict[str, Machine]:
    """Load every parseable .mk in `directory`, keyed by name. Malformed siblings are
    skipped (the caller validates its own target explicitly), so one bad file in the
    project directory can't sink an unrelated run."""
    reg: dict[str, Machine] = {}
    for f in sorted(Path(directory).glob("*.mk")):
        try:
            m = load_machine(f, validate=validate)
        except Exception:  # noqa: BLE001 — a broken sibling shouldn't crash the run
            continue
        reg[m.name] = m
    return reg
