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


def _when_line_has_unquoted_hash(line: str) -> bool:
    """True when a raw `- when: …` line risks YAML treating `#` as a comment.

    Plain (unquoted) scalars end at the first `` #`` (trailing comment). Authors
    often write markdown headings like ``## Section`` *inside* the condition and
    silently truncate it. Fully quoted ``when`` values are fine. A trailing
    comment after a complete token (``when: otherwise # finish``) is fine too.
    """
    stripped = line.lstrip()
    if not stripped.startswith("- when:"):
        return False
    value = stripped[len("- when:") :].strip()
    if not value:
        return False
    # Fully quoted scalar (single line): # inside quotes is not a YAML comment.
    if (value.startswith('"') and value.rstrip().endswith('"') and len(value) >= 2) or (
        value.startswith("'") and value.rstrip().endswith("'") and len(value) >= 2
    ):
        return False
    # Strip a trailing YAML comment (` # …`) from an unquoted scalar, then look
    # for `#` that was *inside* the intended condition (esp. markdown `##`).
    core = value.split(" #", 1)[0].rstrip()
    if not core or core.lower() == "otherwise":
        return False
    return "#" in core


def _catch_all_findings(sid: str, s: State, repair_only: bool) -> list[str]:
    """`missing-catch-all`: the state's transition relation is partial (SPEC §5).

    A state's gates are a *relation*, not a function: hooks return False, and since
    the fused judge may answer "none of the above" a prose batch can reject every
    condition. Evaluation then runs off the end of the gate list and the run halts
    with `no-gate-matched`. Only a `when: otherwise` gate makes the transition
    function **total** — and only if it is still eligible, which a `repair` gate
    stops being once its budget is spent (it also disables the `judge-unparseable`
    soft-fallback, which needs an eligible catch-all).
    """
    catch_alls = [g for g in s.gates if g.when.strip().lower() == "otherwise"]
    if not catch_alls:
        # repair-only states already get a more specific finding; don't say it twice.
        if repair_only:
            return []
        return [
            f"{sid}: no catch-all gate — every gate is conditional, so a state whose "
            "conditions are all false halts the run with no-gate-matched; end the "
            "state with a `when: otherwise` gate"
        ]
    if all(g.kind == "repair" for g in catch_alls):
        return [
            f"{sid}: the only `when: otherwise` gate is a repair — once its budget is "
            "spent the state has no eligible catch-all (no-gate-matched, and no "
            "soft-fallback for an unparseable judge); add a non-repair catch-all"
        ]
    return []


def lint_source(text: str) -> list[str]:
    """Source-level smells that need the raw YAML (not only the parsed machine)."""
    findings: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if _when_line_has_unquoted_hash(line):
            findings.append(
                f"line {i}: gate `when` contains unquoted '#' — YAML may treat it as a "
                "comment and truncate the condition; quote the whole when string "
                '(e.g. when: "… ## Section …")'
            )
    return findings


def lint_machine(machine: Machine, *, source: str | None = None) -> list[str]:
    """Return advisory findings (never errors — those belong to semantic_check).

    Pass ``source`` (raw .mkl text) to also run source-level checks (e.g. unquoted
    ``#`` in ``when`` lines that YAML comment-truncates before parse).
    """
    findings: list[str] = []
    if source is not None:
        findings.extend(lint_source(source))
    refs = _referenced_roots(machine)
    escalate_states: list[str] = []

    for sid, s in machine.states.items():
        # Dead gates: `otherwise` always fires when reached, so anything after it is unreachable.
        for i, g in enumerate(s.gates):
            if g.when.strip().lower() == "otherwise" and i < len(s.gates) - 1:
                findings.append(
                    f"{sid}: {len(s.gates) - 1 - i} gate(s) after 'otherwise' can never fire"
                )
                break
            if g.kind == "escalate":
                escalate_states.append(sid)
        # Repair-only states are a guaranteed no-gate-matched halt once budgets exhaust.
        repair_only = bool(s.gates) and all(g.kind == "repair" for g in s.gates)
        if repair_only:
            findings.append(
                f"{sid}: every gate is a repair — once repair budgets exhaust the run "
                "halts with no-gate-matched; add an ok/escalate/fail route"
            )
        findings.extend(_catch_all_findings(sid, s, repair_only))
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

    # One advisory per machine: prose escalate is control-flow-critical and
    # non-deterministic under repeats (gate-divergence 2026-07-24:
    # severity_escalate agreement 0.667). Prefer --hitl or code-hook gates on
    # production page/approve paths (SPEC §11) — not a hard error (tier-cascade
    # escalate to a stronger state is a valid pattern).
    if escalate_states:
        where = ", ".join(dict.fromkeys(escalate_states))  # preserve order, uniq
        # Prefixed "note:" so `lint --strict` still fails only on structural smells
        # (dead gates, repair-only, unresolved templates) — escalate is intentional
        # for tier-cascade (SPEC §10) as well as HITL. Production hosts still need
        # --hitl / hooks on page/approve paths (SPEC §11).
        findings.append(
            f"note: machine uses escalate on [{where}]: prose escalate is "
            "non-deterministic under provider/repeats — for production control-flow "
            "prefer --hitl or a code-hook gate (SPEC §11); "
            "see docs/experiments/gate-divergence.md"
        )

    findings.extend(_unresolved_interpolation(machine))
    return findings
