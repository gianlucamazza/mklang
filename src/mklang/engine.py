"""The mklang runtime: executes a Machine against an LLM (SPEC §6)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .interpolate import fmt, lookup, render
from .model import Machine, State

MAX_CALL_DEPTH = 8
_OVER_VAR = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


@dataclass
class RunResult:
    status: str  # "done" | "halt"
    trace: list[dict]
    context: dict
    result: object = None
    error: str | None = None
    at: str | None = None


def _model_for(state: State, machine: Machine, tiers: dict) -> str:
    return tiers[state.tier or machine.default_tier]


def _system(state: State) -> str:
    return (
        "You are executing ONE state of an mklang state machine.\n"
        f"OUTPUT SHAPE (structure): {state.structure}\n"
        f"OPERATIONAL POLICY (execution): {state.execution or 'none'}\n"
        "Return ONLY the described output — no preamble, no explanation."
    )


@dataclass
class _Ctx:
    """Shared execution dependencies threaded through the run."""

    llm: object
    tiers: dict
    judge_model: str
    registry: dict
    tier_params: dict  # tier -> provider-specific params
    max_workers: int = 5


def _exec_one(state: State, ctx: dict, feedback: str, deps: _Ctx, machine: Machine, depth: int):
    """Execute a state once → (output, sub_trace|None, reasoning|None)."""
    if state.kind == "call":
        sub_input = {k: render(v, ctx) for k, v in (state.input or {}).items()}
        sub_machine = deps.registry.get(state.call)
        if sub_machine is None:
            raise KeyError(f"call: unknown machine {state.call!r}")
        sub = run(
            sub_machine,
            {**sub_machine.context, **sub_input},
            deps.registry,
            deps.llm,
            deps.tiers,
            deps.judge_model,
            depth=depth + 1,
            max_workers=deps.max_workers,
            tier_params=deps.tier_params,
        )
        return sub.result, sub.trace, None
    tier = state.tier or machine.default_tier
    model = deps.tiers[tier]
    params = deps.tier_params.get(tier)
    user = render(state.prompt, ctx) + (f"\n\n[Repair feedback] {feedback}" if feedback else "")
    temperature = 0.8 if state.sample else 0.4
    p = deps.llm.produce(
        model, _system(state), user, reason=state.reason, temperature=temperature, params=params
    )
    return p.text, None, p.reasoning


def _safe_exec(state, ctx, deps, machine, depth):
    """Execute one fan-out branch; a branch failure becomes a marker, not a crash."""
    try:
        return _exec_one(state, ctx, "", deps, machine, depth)
    except Exception as e:  # noqa: BLE001 — isolate the branch
        return (f"[branch-error: {e}]", None, None)


def _branch_contexts(state: State, ctx: dict) -> list[dict]:
    if state.sample:
        return [dict(ctx) for _ in range(state.sample)]
    m = _OVER_VAR.search(state.over or "")  # extract the path from "{{chunks}}"
    items = lookup(ctx, m.group(1)) if m else None
    if not isinstance(items, list):
        items = []
    out = []
    for i, item in enumerate(items):
        b = dict(ctx)
        b["item"], b["index"] = item, i
        out.append(b)
    return out


def run(
    machine: Machine,
    context: dict,
    registry: dict,
    llm,
    tiers: dict,
    judge_model: str,
    depth: int = 0,
    max_workers: int = 5,
    tier_params: dict | None = None,
) -> RunResult:
    if depth > MAX_CALL_DEPTH:
        return RunResult("halt", [], dict(context), error="call-depth-exceeded")
    deps = _Ctx(llm, tiers, judge_model, registry, tier_params or {}, max_workers)
    ctx = dict(context)
    state_id = machine.entry
    trace: list[dict] = []
    steps = 0
    feedback = ""
    repair_left: dict[tuple[str, int], int] = {}

    while True:
        if steps >= machine.budget:
            return RunResult("halt", trace, ctx, error="budget-exhausted")
        S = machine.states[state_id]
        step: dict = {"state": state_id, "tier": S.tier or machine.default_tier}

        # 1) EXECUTE (isolate failures: single → halt cleanly, branch → marker)
        if S.is_fanout:
            branches = _branch_contexts(S, ctx)
            steps += max(1, len(branches))
            if branches:
                with ThreadPoolExecutor(max_workers=deps.max_workers) as ex:
                    outs = list(ex.map(lambda b: _safe_exec(S, b, deps, machine, depth), branches))
            else:
                outs = []
            result = [o[0] for o in outs]
            subs = [o[1] for o in outs if o[1] is not None]
            step["branches"] = [o[0] if isinstance(o[0], str) else fmt(o[0]) for o in outs]
            if subs:
                step["sub_trace"] = subs
            if S.reason:
                step["reasonings"] = [o[2] for o in outs]
        else:
            steps += 1
            try:
                out, sub, reasoning = _exec_one(S, ctx, feedback, deps, machine, depth)
            except Exception as e:  # noqa: BLE001 — surface as a clean halt, not a traceback
                return RunResult("halt", trace, ctx, error=f"state-error: {e}", at=state_id)
            result = out
            step["output"] = out if isinstance(out, str) else fmt(out)
            if reasoning:
                step["reasoning"] = reasoning
            if sub is not None:
                step["sub_trace"] = sub
        feedback = ""

        # 2) DEPOSIT
        if S.accumulate:
            prev = ctx.get(S.output, [])
            if not isinstance(prev, list):
                prev = [prev]
            ctx[S.output] = prev + [result]
        else:
            ctx[S.output] = result

        # 3) JUDGE (skip repair gates whose budget is exhausted)
        eligible = [
            (i, g)
            for i, g in enumerate(S.gates)
            if not (g.kind == "repair" and repair_left.get((state_id, i), g.repair) == 0)
        ]
        if not eligible:  # every gate was a repair with an exhausted budget
            step.update(step=steps, gate=None, policy="no-gate-matched", to=None)
            trace.append(step)
            return RunResult("halt", trace, ctx, error="no-gate-matched", at=state_id)
        gi_local = deps.llm.judge(deps.judge_model, [g.when for _, g in eligible], fmt(result), ctx)
        gi_local = max(0, min(gi_local, len(eligible) - 1))  # trust nothing from the judge
        i, gate = eligible[gi_local]
        step.update(step=steps, gate=gate.when, policy=gate.kind, to=gate.to)
        trace.append(step)

        # 4) TRANSITION
        if gate.kind == "fail":
            return RunResult("halt", trace, ctx, error="gate-fail", at=state_id)
        if gate.kind == "repair":
            repair_left[(state_id, i)] = repair_left.get((state_id, i), gate.repair) - 1
            feedback = f"The previous attempt did not satisfy: '{gate.when}'. Fix it."
        if gate.to == "END":
            rv = ctx.get(machine.result) if machine.result else result
            return RunResult("done", trace, ctx, result=rv)
        state_id = gate.to
