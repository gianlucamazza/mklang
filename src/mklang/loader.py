"""Load and validate a .mk file: JSON-Schema (structure) + semantic checks."""

from __future__ import annotations

import functools
import json
from pathlib import Path

import jsonschema
import yaml

from .model import Machine, parse_machine


@functools.lru_cache(maxsize=1)
def _schema() -> dict:
    """Load the JSON Schema — bundled package copy first (works pip-installed),
    else the repo-root schema/ when running in-tree."""
    try:
        from importlib.resources import files

        text = files("mklang").joinpath("data/mklang.schema.json").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        repo_schema = Path(__file__).resolve().parents[2] / "schema" / "mklang.schema.json"
        text = repo_schema.read_text(encoding="utf-8")
    return json.loads(text)


def load_dict(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def validate_dict(d: dict) -> None:
    jsonschema.validate(d, _schema())


def load_machine(path: str | Path, validate: bool = True) -> Machine:
    d = load_dict(path)
    if validate:
        validate_dict(d)
    return parse_machine(d)


def semantic_check(machine: Machine, registry: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block a run; warnings are advisory."""
    errors: list[str] = []
    warnings: list[str] = []
    ids = set(machine.states)

    if machine.entry not in ids:
        errors.append(f"entry '{machine.entry}' is not a state")

    produced = {s.output for s in machine.states.values()}
    declared_tools = {t.get("name") for t in machine.tools}
    for sid, s in machine.states.items():
        for g in s.gates:
            if g.kind != "fail" and g.to != "END" and g.to not in ids:
                errors.append(f"{sid}: gate -> unknown state '{g.to}'")
        if s.kind == "call" and s.call not in registry:
            errors.append(f"{sid}: call -> unknown machine '{s.call}'")
        if s.kind == "tool" and machine.tools and s.tool not in declared_tools:
            warnings.append(f"{sid}: tool '{s.tool}' is not declared in the machine's tools:")
        # a multi-gate state without a catch-all can leave no transition firing
        if len(s.gates) > 1 and not any(g.when.strip().lower() == "otherwise" for g in s.gates):
            warnings.append(f"{sid}: no 'otherwise' catch-all gate (a transition may fail to fire)")

    if machine.result and machine.result not in produced:
        warnings.append(f"result key '{machine.result}' is not produced by any state's output")

    # reachability of END from entry
    seen: set[str] = set()
    stack = [machine.entry]
    while stack:
        cur = stack.pop()
        if cur in seen or cur == "END" or cur not in machine.states:
            continue
        seen.add(cur)
        for g in machine.states[cur].gates:
            if g.to and g.to not in seen:
                stack.append(g.to)
    if not any(g.to == "END" for sid in seen for g in machine.states[sid].gates):
        errors.append("no reachable path to END")
    for dead in sorted(ids - seen):
        warnings.append(f"{dead}: unreachable state (never entered from '{machine.entry}')")

    return errors, warnings


def used_tiers(machine: Machine) -> set[str]:
    """Capability tiers a run will resolve against the provider map.

    Generative and call states use `state.tier or default_tier`. Tool states never
    call the LLM, so they contribute nothing unless they override tier (schema forbids
    tier on tools today)."""
    tiers: set[str] = {machine.default_tier}
    for s in machine.states.values():
        if s.kind == "tool":
            continue
        tiers.add(s.tier or machine.default_tier)
    return tiers


def check_tiers(machine: Machine, provider_tiers: dict) -> list[str]:
    """Return errors if the machine needs a tier missing from the provider map."""
    available = set(provider_tiers)
    missing = sorted(used_tiers(machine) - available)
    if not missing:
        return []
    return [
        f"tier(s) {missing} not in provider map (available: {sorted(available)})"
    ]
