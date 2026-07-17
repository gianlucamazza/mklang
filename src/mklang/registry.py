"""Machine registry: load every .mk in a directory, keyed by `machine:` name,
plus the bundled `std_*` stdlib and `mklang.machines` entry-point plugins."""

from __future__ import annotations

import functools
import sys
from importlib.metadata import entry_points
from pathlib import Path

import yaml

from .loader import load_machine
from .model import Machine, parse_machine

ENTRY_POINT_GROUP = "mklang.machines"


def load_registry(directory: str | Path, validate: bool = True) -> dict[str, Machine]:
    """Load every parseable .mk in `directory`, keyed by name. Malformed siblings are
    skipped (the caller validates its own target explicitly), so one bad file in the
    project directory can't sink an unrelated run."""
    reg: dict[str, Machine] = {}
    for f in sorted(Path(directory).glob("*.mk")):
        try:
            m = load_machine(f, validate=validate)
        except Exception:  # a broken sibling shouldn't crash the run
            continue
        reg[m.name] = m
    return reg


@functools.lru_cache(maxsize=1)
def load_stdlib_registry() -> dict[str, Machine]:
    """The bundled `std_*` architecture machines — package copy first (works
    pip-installed), else the repo tree. Schema validation is pinned by the test
    suite, not repeated per run."""
    reg: dict[str, Machine] = {}
    try:
        from importlib.resources import files

        stdlib = files("mklang").joinpath("data/stdlib")
        entries = [e for e in stdlib.iterdir() if e.name.endswith(".mk")]
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        entries = sorted((Path(__file__).resolve().parent / "data" / "stdlib").glob("*.mk"))
    for e in sorted(entries, key=lambda x: x.name):
        try:
            m = parse_machine(yaml.safe_load(e.read_text(encoding="utf-8")))
        except Exception as err:  # a broken stdlib file must not sink runs
            print(f"# warning: stdlib machine {e.name!r} failed to load: {err}", file=sys.stderr)
            continue
        reg[m.name] = m
    return reg


def load_entry_point_machines(group: str = ENTRY_POINT_GROUP) -> dict[str, Machine]:
    """Load third-party machines from packaging entry points.

    The loaded object must be a machine document (dict) or a zero-arg factory
    returning one; it is parsed with `parse_machine` and keyed by its `machine:`
    name. Failures are skipped with a stderr warning so a broken plugin cannot
    sink the CLI."""
    reg: dict[str, Machine] = {}
    try:
        eps = entry_points()
        selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])
    except Exception as e:
        print(f"# warning: could not read entry points ({group}): {e}", file=sys.stderr)
        return reg
    for ep in selected:
        try:
            obj = ep.load()
            if callable(obj):
                obj = obj()
            if not isinstance(obj, dict):
                raise TypeError(f"{ep.name} is not a machine document (dict)")
            m = parse_machine(obj)
            reg[m.name] = m
        except Exception as e:
            print(f"# warning: machine plugin {ep.name!r} failed to load: {e}", file=sys.stderr)
    return reg


def base_registry(*, include_entry_points: bool = True) -> dict[str, Machine]:
    """Stdlib ← entry-point plugins (later keys win); callers layer sibling
    machines and the run target on top, so user machines always shadow these."""
    reg = dict(load_stdlib_registry())
    if include_entry_points:
        reg.update(load_entry_point_machines())
    return reg
