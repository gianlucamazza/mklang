"""LLM-assisted lint (ADR 0010): probe prose-gate ambiguity with a live judge.

For each state with >= 2 prose conditions, generate K synthetic outputs that
plausibly satisfy the state's `structure` (one produce call), then ask the real
gate judge which condition fires, R times per output. Two advisory signals:

- instability — one output routes to different gates across repeats;
- overlap — two conditions that both claim the same output (across repeats).

Findings are a SIGNAL, never a gate: results are non-deterministic by design,
depend on provider/tier/temperature, and absence of a finding is not proof of
unambiguous gates. `--strict` must not promote them to errors.
"""

from __future__ import annotations

from .engine import _parse_list
from .errors import JudgeUnparseable
from .model import Machine, State


def _prose_conditions(state: State) -> list[str]:
    """The judged batch: prose gates only — no hooks, no `otherwise` catch-all."""
    return [g.when for g in state.gates if not g.hook and g.when.strip().lower() != "otherwise"]


def _synthesis_prompt(state: State, conditions: list[str], k: int) -> str:
    listed = "\n".join(f"- {c}" for c in conditions)
    return (
        f"You are stress-testing the exit conditions of a state machine step.\n"
        f"The step's output contract is:\n{state.structure or '(unspecified)'}\n\n"
        f"The exit conditions to discriminate between are:\n{listed}\n\n"
        f"Write {k} DIFFERENT plausible outputs for this step: include clear-cut "
        f"cases for each condition and at least two borderline cases that sit "
        f"between conditions. Reply with ONLY a JSON array of {k} strings."
    )


def _judge_once(llm, model: str, conditions: list[str], output: str) -> int | None:
    """One real judge call; None when the judge picks no listed condition."""
    try:
        verdict = llm.judge(model, conditions, output, {})
    except JudgeUnparseable:
        return None
    choice = verdict[0] if isinstance(verdict, tuple) else verdict
    if not isinstance(choice, int) or choice < 0 or choice >= len(conditions):
        return None
    return choice


def llm_lint_machine(
    machine: Machine,
    llm,
    tiers: dict,
    judge: str | None = None,
    *,
    samples: int = 5,
    repeats: int = 3,
    tier_params: dict | None = None,
) -> list[str]:
    """Advisory findings for every multi-prose-gate state. Live LLM calls:
    per state, 1 produce + samples*repeats judge calls."""
    findings: list[str] = []
    for sid, state in machine.states.items():
        conditions = _prose_conditions(state)
        if len(conditions) < 2:
            continue
        tier = state.tier or machine.default_tier
        model = tiers[tier]
        judge_model = judge or model
        params = (tier_params or {}).get(tier)
        produced = llm.produce(
            model,
            "You produce test data. Reply with JSON only.",
            _synthesis_prompt(state, conditions, samples),
            temperature=0.8,
            params=params,
        )
        try:
            outputs = [str(o) for o in _parse_list(produced.text)][:samples]
        except ValueError as e:
            findings.append(f"{sid}: could not synthesize test outputs ({e}) — state skipped")
            continue
        unstable = 0
        overlap: dict[tuple[int, int], int] = {}
        for out in outputs:
            picks = {_judge_once(llm, judge_model, conditions, out) for _ in range(repeats)}
            real = sorted(p for p in picks if p is not None)
            if len(picks) > 1:
                unstable += 1
            for i in range(len(real)):
                for j in range(i + 1, len(real)):
                    pair = (real[i], real[j])
                    overlap[pair] = overlap.get(pair, 0) + 1
        n = len(outputs)
        if unstable:
            findings.append(
                f"{sid}: unstable routing on {unstable}/{n} synthetic outputs "
                f"(judge={judge_model}, repeats={repeats}) — ambiguous prose conditions"
            )
        for (i, j), count in sorted(overlap.items()):
            findings.append(
                f"{sid}: conditions {i} ({conditions[i]!r}) and {j} ({conditions[j]!r}) "
                f"overlap on {count}/{n} synthetic outputs — tighten or reorder"
            )
    return findings
