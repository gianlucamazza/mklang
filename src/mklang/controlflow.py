"""Control-flow taint: untrusted data must not, by itself, choose an effect.

ADR 0025 fences untrusted values so a model can tell data from directives. That
protects the *text* a state reads. It says nothing about the *decision* a gate
makes after reading it: a prose gate judged over a tool observation or a
host-supplied input picks the next state, and nothing in the language stopped
that state from being a `tool:` state that writes a file or sends a reply. An
injection that talks the judge into firing `ok → send` violates no invariant —
the run is behaving exactly as specified.

This module supplies the two static ingredients of the rule in SPEC §6
("Control-flow taint"); the engine tracks the dynamic half:

- **What counts as an effect.** Only `tool:` states can act on the world
  (generative `execution` cannot invoke host tools, SPEC §6), so the effect
  surface is exactly the tool registry, split into read-only and effectful.
  Unknown tools — every third-party plugin — are **effectful by default**: a
  host that knows better says so, silence is not a safety claim.
- **Whether a `call` can act.** A sub-machine's result is external data if the
  sub-machine (transitively) can reach a tool state at all.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .model import Machine

# Effect class of the package builtins. "read" tools observe the world without
# changing it; "effect" tools change something a user would notice.
TOOL_EFFECTS: dict[str, str] = {
    "calc": "read",  # pure arithmetic, no I/O at all
    "search": "read",
    "search_kb": "read",
    "list_files": "read",
    "read_file": "read",
    "write_file": "effect",  # writes to the workspace (grant-gated, ADR 0024)
    "send_reply": "effect",  # leaves the host (stub by default, ADR 0020)
    # Console host tools (mklang.console.tools). Bundled with the package, so
    # they are classified here rather than left to the unknown-tool default.
    "list_machines": "read",
    "describe_machine": "read",
    "read_machine": "read",
    "check_machine": "read",
    "list_workspace": "read",
    "read_workspace_file": "read",
    "search_workspace": "read",
    "ask_user": "read",  # asks a human and returns the answer; changes nothing
    "write_machine": "effect",  # writes a .mkl into the workspace
    "run_machine": "effect",  # executes another machine, tools and all
    "update_task": "effect",  # mutates the console's task list
}

# Host policies for a tainted decision reaching an effectful state.
FLOW_POLICIES = ("report", "halt")


def is_effectful(tool: str | None, overrides: Mapping[str, str] | None = None) -> bool:
    """True when running `tool` can change something outside the run.

    Resolution order: host `overrides` → package `TOOL_EFFECTS` → **effectful**.
    The default is the unsafe-looking one on purpose: an unclassified tool is one
    nobody has thought about, and treating it as read-only would silently exempt
    exactly the plugins this rule exists for."""
    if tool is None:
        return False
    if overrides and tool in overrides:
        return overrides[tool] == "effect"
    return TOOL_EFFECTS.get(tool, "effect") == "effect"


def _reaches_tool(
    machine: Machine | None,
    registry: Mapping[str, Machine],
    counts: Callable[[str | None], bool],
    seen: frozenset[str],
) -> bool:
    """Does `machine` reach a `tool:` state `counts` accepts, following `call:` edges?

    Reachability, not path feasibility — a deliberate over-approximation shared by
    both callers below."""
    if machine is None or machine.name in seen:
        return False
    seen = seen | {machine.name}
    for state in machine.states.values():
        if state.kind == "tool" and counts(state.tool):
            return True
        if state.kind == "call" and _reaches_tool(
            registry.get(state.call or ""), registry, counts, seen
        ):
            return True
    return False


def machine_touches_tools(
    machine: Machine | None,
    registry: Mapping[str, Machine],
    _seen: frozenset[str] = frozenset(),
) -> bool:
    """True when `machine` can reach a `tool:` state, following `call:` edges.

    Used to decide whether a `call` result is external data. The over-approximation
    is deliberate: the cost of being wrong is asymmetric — a false "external" costs
    one extra confirmation, a false "trusted" costs the invariant."""
    return _reaches_tool(machine, registry, lambda _tool: True, _seen)


def machine_touches_effects(
    machine: Machine | None,
    registry: Mapping[str, Machine],
    overrides: Mapping[str, str] | None = None,
    _seen: frozenset[str] = frozenset(),
) -> bool:
    """True when `machine` can reach an **effectful** `tool:` state.

    The effect surface does not stop at a `call:` boundary — a sub-machine acts on
    the world through the same tool registry — so the static check in `lint` needs
    this whenever a registry is available to resolve `call:` targets."""
    return _reaches_tool(machine, registry, lambda tool: is_effectful(tool, overrides), _seen)
