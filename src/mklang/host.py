"""Host wiring: the shared seam every surface (CLI, MCP) uses to commission a run.

Pure functions — no printing, no exit codes, no filesystem writes. Failures raise
`PrepareError` with structured `errors`/`warnings`; each surface renders them its
own way (stderr lines for the CLI, payload fields for the MCP server).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jsonschema
import yaml

from .config import ProviderConfig, load_provider
from .engine import RunResult
from .loader import check_tiers, load_machine, semantic_check, validate_dict
from .model import Machine, parse_machine
from .registry import base_registry, load_registry


class PrepareError(Exception):
    """Preparation failed. `kind` is "load" (YAML/schema/IO) or "semantic"."""

    def __init__(
        self, errors: list[str], warnings: list[str] | None = None, kind: str = "semantic"
    ):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings or []
        self.kind = kind


@dataclass
class Prepared:
    prov: ProviderConfig
    llm: object
    registry: dict[str, Machine]
    machine: Machine
    tools: dict
    hooks: dict
    warnings: list[str]


def _default_build_llm(prov):
    from .providers import build_llm

    return build_llm(prov)


def _provider(
    config: str, provider: str | None, build_llm
) -> tuple[ProviderConfig, object, list[str]]:
    prov = load_provider(config, provider)
    warnings = []
    if not prov.api_key and prov.name != "local":
        warnings.append(f"no API key for provider '{prov.name}' — set it in .env")
    llm = (build_llm or _default_build_llm)(prov)
    return prov, llm, warnings


def _check(prov, machine, registry, strict, warnings: list[str]) -> tuple[dict, dict]:
    """Semantic/tier checks + tool/hook registries. Appends to `warnings`, raises on errors."""
    errors, more = semantic_check(machine, registry, strict=strict)
    errors.extend(check_tiers(machine, prov.tiers))
    warnings.extend(more)
    if errors:
        raise PrepareError(errors, warnings)
    from .hooks import load_hook_registry
    from .tools import load_tool_registry

    tools = load_tool_registry()
    hooks = load_hook_registry()
    for sid, s in machine.states.items():
        if s.kind == "tool" and s.tool not in tools:
            warnings.append(
                f"state '{sid}' uses tool '{s.tool}' not in the registry "
                f"{sorted(tools)} — the run halts if it is reached"
            )
        for g in s.gates:
            if g.hook and g.hook not in hooks:
                warnings.append(
                    f"state '{sid}' uses hook '{g.hook}' not in the registry "
                    f"{sorted(hooks)} — the run halts if it is reached"
                )
    return tools, hooks


def _parse_source(source: str, warnings: list[str]) -> Machine:
    """Inline `.mk` source string → Machine: YAML → schema → parse."""
    try:
        d = yaml.safe_load(source)
    except yaml.YAMLError as e:
        raise PrepareError([f"invalid YAML: {e}"], warnings, kind="load") from e
    if not isinstance(d, dict):
        raise PrepareError(
            ["source is not a mapping (a .mk document is a YAML mapping)"], warnings, kind="load"
        )
    try:
        validate_dict(d)
    except jsonschema.ValidationError as e:
        raise PrepareError([f"schema: {e.message}"], warnings, kind="load") from e
    return parse_machine(d)


def check_machine(
    source: str | None = None, path: str | None = None, *, strict: bool = False
) -> dict:
    """Validate without running — schema + semantics + lint, no provider needed.
    Mirrors `mklang check`/`lint` (no tier check: that needs a provider config)."""
    from .lint import lint_machine

    base = base_registry()
    try:
        if source is not None:
            machine = _parse_source(source, [])
            registry = {**base, machine.name: machine}
        else:
            registry = {**base, **load_registry(Path(path).parent, validate=False)}
            machine = load_machine(path)
            registry[machine.name] = machine
    except PrepareError as e:
        return {"ok": False, "errors": e.errors, "warnings": e.warnings, "lint": []}
    except Exception as e:  # load/validation failure of a path machine
        return {"ok": False, "errors": [getattr(e, "message", str(e))], "warnings": [], "lint": []}
    errors, warnings = semantic_check(machine, registry, strict=strict)
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "lint": lint_machine(machine),
    }


def prepare_path(
    config: str,
    provider: str | None,
    machine_path: str,
    *,
    strict: bool = False,
    build_llm=None,
) -> Prepared:
    """Load a machine from disk with sibling-`.mk` registry discovery, layered on
    the bundled stdlib. `machine_path` may also be a bare registry name (e.g.
    `std_cot`) when no such file exists — run-by-name, no sibling discovery."""
    prov, llm, warnings = _provider(config, provider, build_llm)
    base = base_registry()
    if not Path(machine_path).exists():
        if machine_path in base:
            registry = base
            machine = base[machine_path]
            tools, hooks = _check(prov, machine, registry, strict, warnings)
            return Prepared(prov, llm, registry, machine, tools, hooks, warnings)
        raise PrepareError(
            [f"no such file or bundled machine: '{machine_path}' (bundled: {sorted(base)})"],
            warnings,
            kind="load",
        )
    siblings = load_registry(Path(machine_path).parent, validate=False)
    for name in sorted(set(siblings) & set(base)):
        warnings.append(f"machine '{name}' shadows the bundled stdlib machine")
    registry = {**base, **siblings}
    try:
        machine = load_machine(machine_path)
    except Exception as e:  # surface load/validation failure cleanly
        raise PrepareError([getattr(e, "message", str(e))], warnings, kind="load") from e
    if machine.name in base and machine.name not in siblings:
        warnings.append(f"machine '{machine.name}' shadows the bundled stdlib machine")
    registry[machine.name] = machine
    tools, hooks = _check(prov, machine, registry, strict, warnings)
    return Prepared(prov, llm, registry, machine, tools, hooks, warnings)


def prepare_source(
    config: str,
    provider: str | None,
    source: str,
    *,
    strict: bool = False,
    build_llm=None,
) -> Prepared:
    """Load a machine from an inline `.mk` source string; the registry holds it plus
    the bundled stdlib (`call: std_*` works), so a `call:` to any other unsupplied
    target surfaces as a semantic error."""
    prov, llm, warnings = _provider(config, provider, build_llm)
    machine = _parse_source(source, warnings)
    registry = base_registry()
    if machine.name in registry:
        warnings.append(f"machine '{machine.name}' shadows the bundled stdlib machine")
    registry[machine.name] = machine
    tools, hooks = _check(prov, machine, registry, strict, warnings)
    return Prepared(prov, llm, registry, machine, tools, hooks, warnings)


def build_output(res: RunResult) -> dict:
    """The wire shape of a run result; surfaces add their own `checkpoint` key."""
    out = {
        "status": res.status,
        "error": res.error,
        "result": res.result,
        "usage": res.usage,
        "trace": res.trace,
    }
    if res.at is not None:
        out["at"] = res.at
    return out


def describe_machine(m: Machine, source: str | None = None) -> dict:
    """The commissionable contract of a machine: what to set, what comes back."""
    out = {
        "name": m.name,
        "entry": m.entry,
        "budget": m.budget,
        "default_tier": m.default_tier,
        "result": m.result,
        "context": dict(m.context),
        "states": [
            {
                "id": sid,
                "kind": s.kind,
                **({"tier": s.tier} if s.tier else {}),
                "output": s.output,
                "gates": len(s.gates),
            }
            for sid, s in m.states.items()
        ],
    }
    if source is not None:
        out["source"] = source
    return out


def set_path(ctx: dict, dotted_key: str, value) -> None:
    """Assign `value` at a dotted path in `ctx`, creating intermediate dicts."""
    cur = ctx
    parts = dotted_key.split(".")
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value
