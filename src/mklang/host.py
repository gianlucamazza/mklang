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

from collections.abc import Callable

from .config import ProviderConfig, load_provider
from .engine import RunResult
from .llm.base import LLM
from .loader import check_tiers, load_machine, semantic_check, validate_dict
from .model import Machine, parse_machine
from .registry import base_registry, load_registry


class PrepareError(Exception):
    """Preparation failed. `kind` is "load" (YAML/schema/IO), "semantic", or
    "config" (host configuration, e.g. a missing provider API key)."""

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
    llm: LLM
    registry: dict[str, Machine]
    machine: Machine
    tools: dict
    hooks: dict
    warnings: list[str]


# A host may swap the LLM factory (tests, embedders); the default builds the
# configured provider adapter.
BuildLLM = Callable[["ProviderConfig"], "LLM"]


def _default_build_llm(prov: ProviderConfig) -> LLM:
    from .providers import build_llm

    return build_llm(prov)


def missing_key_message(prov: ProviderConfig) -> str | None:
    """An actionable diagnostic when the provider has no API key; None when fine.

    The `local` provider is exempt (local OpenAI-compatible servers rarely need
    a key); for other keyless endpoints, set any placeholder value in .env.
    """
    if prov.api_key or prov.name == "local":
        return None
    var = prov.api_key_env or "its API key variable"
    return (
        f"no API key for provider '{prov.name}' — set {var} in .env "
        f"(scaffolded by `mklang init`), or use --provider local"
    )


def _provider(
    config: str | None, provider: str | None, build_llm: BuildLLM | None
) -> tuple[ProviderConfig, LLM, list[str]]:
    try:
        prov = load_provider(config, provider)
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise PrepareError([str(exc)], kind="load") from exc
    missing = missing_key_message(prov)
    if missing:
        raise PrepareError([missing], kind="config")
    llm = (build_llm or _default_build_llm)(prov)
    return prov, llm, []


def _check(
    prov: ProviderConfig,
    machine: Machine,
    registry: dict[str, Machine],
    strict: bool,
    warnings: list[str],
) -> tuple[dict, dict]:
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
    """Inline `.mkl` source string → Machine: YAML → schema → parse."""
    try:
        d = yaml.safe_load(source)
    except yaml.YAMLError as e:
        raise PrepareError([f"invalid YAML: {e}"], warnings, kind="load") from e
    if not isinstance(d, dict):
        raise PrepareError(
            ["source is not a mapping (a .mkl document is a YAML mapping)"], warnings, kind="load"
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
            # Callers pass exactly one of source/path.
            assert path is not None
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
    config: str | None,
    provider: str | None,
    machine_path: str,
    *,
    strict: bool = False,
    build_llm: BuildLLM | None = None,
) -> Prepared:
    """Load a machine from disk with sibling-`.mkl` registry discovery, layered on
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
    config: str | None,
    provider: str | None,
    source: str,
    *,
    strict: bool = False,
    build_llm: BuildLLM | None = None,
) -> Prepared:
    """Load a machine from an inline `.mkl` source string; the registry holds it plus
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


# Compact observation budget for surfaces that feed a brain/agent (console).
# Full result and full trace stay on the RunResult / session events; this only
# shapes the (dict)->str observation the brain sees (ADR 0015 + 0017 honesty).
RESULT_OBS_CHARS = 2000


def inject_host_defaults(ctx: dict, *, today: str | None = None, now: str | None = None) -> dict:
    """Fill host-convention keys **only when the machine declared them**.

    Convention (no language change): if the blackboard already has a top-level
    key (from ``context:`` in the ``.mkl``) and its value is still empty/None
    after user inputs, fill it from the host clock. Never invents undeclared
    keys — keeps check/lint and document purity intact.

    * ``today`` — ISO calendar date (``YYYY-MM-DD``).
    * ``now`` — local wall-clock ISO datetime with offset
      (``YYYY-MM-DDTHH:MM:SS±HH:MM``), for questions like "what time is it?".
    """
    if "today" in ctx:
        cur = ctx.get("today")
        if cur is None or cur == "":
            from datetime import date

            ctx["today"] = today if today is not None else date.today().isoformat()
    if "now" in ctx:
        cur = ctx.get("now")
        if cur is None or cur == "":
            from datetime import datetime

            ctx["now"] = (
                now
                if now is not None
                else datetime.now().astimezone().isoformat(timespec="seconds")
            )
    return ctx


def compact_run_observation(res: RunResult, *, result_chars: int = RESULT_OBS_CHARS) -> dict:
    """Wire shape for agent-facing observations: honest about cutoff, compact.

    - Propagates produce truncation (ADR 0018) as top-level ``truncated`` plus a
      compact ``trace`` summary (step count + which states truncated). Full trace
      remains on the engine result / live events, not in this blob.
    - If ``result`` is a long string, clips with an explicit ``…[truncated]``
      marker (ADR 0017 style) and sets ``result_truncated`` — never a silent cut.
    """
    out = build_output(res)
    steps = res.trace or []
    truncated_steps: list[dict] = []
    for s in steps:
        if not isinstance(s, dict) or not s.get("truncated"):
            continue
        entry: dict = {"state": s.get("state")}
        if s.get("finish_reason"):
            entry["finish_reason"] = s["finish_reason"]
        truncated_steps.append(entry)
    produce_truncated = bool(truncated_steps)
    out["trace"] = {
        "steps": len(steps),
        "truncated": produce_truncated,
        "truncated_steps": truncated_steps,
    }
    out["truncated"] = produce_truncated
    if truncated_steps and truncated_steps[0].get("finish_reason"):
        out["finish_reason"] = truncated_steps[0]["finish_reason"]

    result = out.get("result")
    if isinstance(result, str) and result_chars > 0 and len(result) > result_chars:
        marker = "…[truncated]"
        keep = max(0, result_chars - len(marker))
        out["result"] = result[:keep] + marker
        out["result_truncated"] = True
        out["result_full_chars"] = len(result)
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


def set_path(ctx: dict, dotted_key: str, value: object) -> None:
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
