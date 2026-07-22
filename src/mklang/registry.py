"""Machine registry: load every .mk in a directory, keyed by `machine:` name,
plus the bundled `std_*` stdlib and `mklang.machines` entry-point plugins."""

from __future__ import annotations

import functools
import logging
from importlib.metadata import entry_points
from pathlib import Path

import yaml

from .loader import load_machine
from .model import Machine, parse_machine

ENTRY_POINT_GROUP = "mklang.machines"

_log = logging.getLogger("mklang.registry")


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
            _log.warning("stdlib machine %r failed to load: %s", e.name, err)
            continue
        reg[m.name] = m
    return reg


def load_entry_point_machines(group: str = ENTRY_POINT_GROUP) -> dict[str, Machine]:
    """Load third-party machines from packaging entry points.

    The loaded object must be a machine document (dict) or a zero-arg factory
    returning one; it is parsed with `parse_machine` and keyed by its `machine:`
    name. Failures are skipped with a WARNING log line so a broken plugin
    cannot sink the CLI."""
    reg: dict[str, Machine] = {}
    try:
        eps = entry_points()
        selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])
    except Exception as e:
        _log.warning("could not read entry points (%s): %s", group, e)
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
            _log.warning("machine plugin %r failed to load: %s", ep.name, e)
    return reg


def base_registry(*, include_entry_points: bool = True) -> dict[str, Machine]:
    """Stdlib ← plugins ← system ← user (later keys win)."""
    from .paths import machine_layers

    reg = dict(load_stdlib_registry())
    if include_entry_points:
        reg.update(load_entry_point_machines())
    for _source, directory in machine_layers():
        reg.update(load_registry(directory, validate=False))
    return reg


def registry_with_sources(
    project_dir: str | Path | None = None,
) -> tuple[dict[str, Machine], dict[str, str]]:
    """Build the public discovery registry and retain each winning source label."""
    from .paths import machine_layers

    stdlib = load_stdlib_registry()
    reg = dict(stdlib)
    sources = {name: "stdlib" for name in stdlib}
    for name, machine in load_entry_point_machines().items():
        reg[name] = machine
        sources[name] = "plugin"
    for source, directory in machine_layers():
        for name, machine in load_registry(directory, validate=False).items():
            reg[name] = machine
            sources[name] = source
    if project_dir:
        for name, machine in load_registry(project_dir, validate=False).items():
            reg[name] = machine
            sources[name] = "local"
    return reg, sources
