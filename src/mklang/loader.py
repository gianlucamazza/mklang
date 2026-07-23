"""Load and validate a .mkl file: JSON-Schema (structure) + semantic checks."""

from __future__ import annotations

import functools
import json
from collections import deque
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


def shortest_path_to_end(machine: Machine) -> int | None:
    """Fewest states on any path from `entry` to a gate `to: END` (None if none).

    A step count, not an edge count: entering the entry state is 1 step, and a run
    completes the k-state path `entry → … → sk(gate to END)` iff `budget ≥ k` (the
    engine checks `steps >= budget` at the top of each state). **Fan-out states are
    counted as 1** — the real charge is `max(1, len(branches))`, but the branch
    count is data-dependent and unknown at check time, so this is a lower bound on
    the true cost (host pre-validation, not run semantics). BFS pops states in
    nondecreasing distance, so the first END-gated state popped gives the minimum.
    """
    dist = {machine.entry: 1}
    q: deque[str] = deque([machine.entry])
    while q:
        cur = q.popleft()
        d = dist[cur]
        state = machine.states[cur]
        if any(g.to == "END" for g in state.gates):
            return d
        for g in state.gates:
            nxt = g.to
            if nxt and nxt != "END" and nxt in machine.states and nxt not in dist:
                dist[nxt] = d + 1
                q.append(nxt)
    return None


def semantic_check(
    machine: Machine, registry: dict, strict: bool = False
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block a run; warnings are advisory.

    `strict` promotes an unsupported `mklang:` version from a warning to an error
    (`version-unsupported`): running a future-versioned document under a v0.2
    interpreter behind a mere warning is incoherent for a conformance-pinned
    language — semantics may have diverged (F6)."""
    errors: list[str] = []
    warnings: list[str] = []
    ids = set(machine.states)

    if machine.entry not in ids:
        errors.append(f"entry '{machine.entry}' is not a state")

    produced = {s.output for s in machine.states.values()}
    declared_tools = {t.get("name") for t in machine.tools}
    declared_hooks = {h.get("name") for h in machine.hooks}
    for sid, s in machine.states.items():
        for g in s.gates:
            if g.kind != "fail" and g.to != "END" and g.to not in ids:
                errors.append(f"{sid}: gate -> unknown state '{g.to}'")
            if g.hook and machine.hooks and g.hook not in declared_hooks:
                warnings.append(
                    f"{sid}: gate hook '{g.hook}' is not declared in the machine's hooks:"
                )
        if s.kind == "call" and s.call not in registry:
            errors.append(f"{sid}: call -> unknown machine '{s.call}'")
        if s.kind == "tool" and machine.tools and s.tool not in declared_tools:
            warnings.append(f"{sid}: tool '{s.tool}' is not declared in the machine's tools:")
        # a multi-gate state without a catch-all can leave no transition firing
        if len(s.gates) > 1 and not any(g.when.strip().lower() == "otherwise" for g in s.gates):
            warnings.append(f"{sid}: no 'otherwise' catch-all gate (a transition may fail to fire)")
    if machine.result and machine.result not in produced:
        warnings.append(f"result key '{machine.result}' is not produced by any state's output")

    if machine.version and machine.version not in ("0.2", "0.2.0", "0.3"):
        msg = f'mklang version field is {machine.version!r}; this interpreter targets "0.2"/"0.3"'
        if strict:
            errors.append(f"version-unsupported: {msg}")
        else:
            warnings.append(msg)
    if machine.version in ("0.2", "0.2.0") and any(s.parse for s in machine.states.values()):
        warnings.append('`parse:` is a 0.3 face — declare mklang: "0.3"')

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

    # Static budget feasibility: `budget` bounds steps, so a budget below the
    # shortest path to END is a guaranteed `budget-exhausted` halt at run time —
    # detectable now (SPEC §7). Only meaningful when END is reachable and the
    # entry exists (the checks above already error otherwise).
    if machine.entry in ids:
        sp = shortest_path_to_end(machine)
        if sp is not None:
            if machine.budget < sp:
                errors.append(
                    f"budget-infeasible: budget {machine.budget} is below the {sp}-step "
                    f"shortest path to END (fan-out states counted as 1 step — actual "
                    f"branch counts are data-dependent and may push the true cost higher)"
                )
            elif machine.budget < sp + 2:
                warnings.append(
                    f"budget {machine.budget} leaves no headroom above the {sp}-step "
                    f"shortest path to END — a single repair or loop-back would exhaust it"
                )

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
    return [f"tier(s) {missing} not in provider map (available: {sorted(available)})"]
