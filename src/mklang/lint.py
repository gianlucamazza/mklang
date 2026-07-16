"""Static analysis beyond `check`: advisory findings on machine quality.

`semantic_check` (loader.py) gates a run: unknown states, no path to END, missing
tiers. `lint_machine` never blocks — it surfaces smells: dead gates, unread
outputs, template typos, repair-only dead ends.
"""

from __future__ import annotations

import re

from .model import Machine, State

_VAR = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

# Fan-out branch vars: valid ONLY inside a `sample`/`over` state (§4.7). Referenced
# anywhere else they resolve to empty — almost always an authoring mistake.
_FANOUT_ROOTS = {"item", "index"}
# HITL resume drops the human reply under `human` (§7 / ADR 0008); always allowable.
_RESUME_ROOTS = {"human"}


def _templates_of(s: State) -> list[str]:
    """Every interpolatable text on a state (prompt/structure/execution/over/input)."""
    texts = [s.prompt, s.structure, s.execution, s.over]
    texts += [v for v in (s.input or {}).values() if isinstance(v, str)]
    return [t for t in texts if isinstance(t, str)]


def _referenced_roots(machine: Machine) -> set[str]:
    """Root names referenced by any {{path}} template in the machine."""
    roots: set[str] = set()
    for s in machine.states.values():
        for t in _templates_of(s):
            for path in _VAR.findall(t):
                roots.add(path.split(".")[0])
    return roots


def _unresolved_interpolation(machine: Machine) -> list[str]:
    """`unresolved-interpolation`: a `{{path}}` the machine cannot statically resolve.

    Two checks:

    - **First segment.** The valid-root set is the top-level `context:` keys, every
      state's `output:`, and the HITL `human` resume root; `item`/`index` are valid
      only inside a fan-out state. A root nothing provides is flagged.
    - **Second segment (inline context maps only).** When a root resolves to an
      inline dict literal in `context:` (e.g. `ticket: {body: …}`), the second path
      segment is statically known — `{{ticket.bod}}` is a typo for `{{ticket.body}}`.
      It is validated against the map's keys. Skipped when the root is a state
      output or a runtime root (`human`/`item`/`index`) whose shape is unknowable,
      and skipped when the root's context value is not a dict. Anything deeper than
      the second segment stays out of scope (a nested-dict tail can't be pinned to a
      construct the linter models).

    This is presence in the static key set, NOT a flow-sensitive "defined before
    use" analysis: a loop or branch may legitimately read an output produced on an
    earlier visit, so define-before-use is deliberately out of scope for v0.2
    (hosts injecting extra keys at run time should declare them in `context:` with
    placeholders).
    """
    context = machine.context
    outputs = {s.output for s in machine.states.values()}
    provided = set(context) | outputs | _RESUME_ROOTS
    findings: list[str] = []
    for sid, s in machine.states.items():
        seen_roots: set[str] = set()
        seen_dotted: set[str] = set()
        for t in _templates_of(s):
            for path in _VAR.findall(t):
                segs = path.split(".")
                root = segs[0]
                if root not in seen_roots:
                    seen_roots.add(root)
                    if root in _FANOUT_ROOTS:
                        if not s.is_fanout:
                            findings.append(
                                f"{sid}: template references '{{{{{root}}}}}' but the state is "
                                "not a fan-out — item/index exist only inside a sample/over state"
                            )
                    elif root not in provided:
                        findings.append(
                            f"{sid}: template references '{{{{{root}}}}}' but no context key or "
                            f"state output provides '{root}'"
                        )
                # Second-segment check: only against an inline context dict whose
                # shape is statically known (not a state output / runtime root).
                if len(segs) >= 2 and path not in seen_dotted:
                    seen_dotted.add(path)
                    val = context.get(root)
                    if (
                        isinstance(val, dict)
                        and root not in outputs
                        and root not in _FANOUT_ROOTS
                        and root not in _RESUME_ROOTS
                        and segs[1] not in val
                    ):
                        findings.append(
                            f"{sid}: template references '{{{{{path}}}}}' but the inline "
                            f"context map '{root}' has no key '{segs[1]}' "
                            f"(keys: {sorted(val)})"
                        )
    return findings


def lint_machine(machine: Machine) -> list[str]:
    """Return advisory findings (never errors — those belong to semantic_check)."""
    findings: list[str] = []
    refs = _referenced_roots(machine)

    for sid, s in machine.states.items():
        # Dead gates: `otherwise` always fires when reached, so anything after it is unreachable.
        for i, g in enumerate(s.gates):
            if g.when.strip().lower() == "otherwise" and i < len(s.gates) - 1:
                findings.append(
                    f"{sid}: {len(s.gates) - 1 - i} gate(s) after 'otherwise' can never fire"
                )
                break
        # Repair-only states are a guaranteed no-gate-matched halt once budgets exhaust.
        if s.gates and all(g.kind == "repair" for g in s.gates):
            findings.append(
                f"{sid}: every gate is a repair — once repair budgets exhaust the run "
                "halts with no-gate-matched; add an ok/escalate/fail route"
            )
        # Outputs nobody reads are usually a leftover or a mistyped reference
        # elsewhere. Exempt: terminal states (their output is the run's implicit
        # result or a divergent terminal's outcome record) and states with prose
        # gates (the gate judge consumes the output — the sufficiency pattern).
        terminal = any(g.to == "END" for g in s.gates)
        judged = any(not g.hook and g.when.strip().lower() != "otherwise" for g in s.gates)
        if s.output not in refs and s.output != machine.result and not terminal and not judged:
            findings.append(
                f"{sid}: output '{s.output}' is never read "
                "(no template references it, no prose gate judges it, "
                "and it is not the machine result)"
            )

    findings.extend(_unresolved_interpolation(machine))
    return findings
