"""Static analysis beyond `check`: advisory findings on machine quality.

`semantic_check` (loader.py) gates a run: unknown states, no path to END, missing
tiers. `lint_machine` never blocks — it surfaces smells: dead gates, unread
outputs, template typos, repair-only dead ends.
"""

from __future__ import annotations

import re

from .model import Machine

_VAR = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

# Roots the runtime can inject without a context key or state output backing them:
# fan-out branches get `item`/`index`; HITL resumes drop the reply under `human`.
_RUNTIME_ROOTS = {"item", "index", "human"}


def _referenced_roots(machine: Machine) -> set[str]:
    """Root names referenced by any {{path}} template in the machine."""
    roots: set[str] = set()
    for s in machine.states.values():
        texts = [s.prompt, s.structure, s.execution, s.over]
        texts += [v for v in (s.input or {}).values() if isinstance(v, str)]
        for t in texts:
            if isinstance(t, str):
                for path in _VAR.findall(t):
                    roots.add(path.split(".")[0])
    return roots


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

    # Template roots that nothing can provide — the classic silent-typo bug.
    provided = set(machine.context) | {s.output for s in machine.states.values()} | _RUNTIME_ROOTS
    for root in sorted(refs - provided):
        findings.append(
            f"template references '{{{{{root}}}}}' but no context key or state output "
            f"provides '{root}'"
        )

    return findings
