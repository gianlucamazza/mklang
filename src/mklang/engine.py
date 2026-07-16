"""The mklang runtime: executes a Machine against an LLM (SPEC §6)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .errors import CallFailed, JudgeUnparseable, ProviderError, RefusalError
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
    usage: dict | None = None  # {"input_tokens": int, "output_tokens": int}


def _model_for(state: State, machine: Machine, tiers: dict) -> str:
    tier = state.tier or machine.default_tier
    try:
        return tiers[tier]
    except KeyError:
        raise KeyError(
            f"tier {tier!r} not configured (available: {sorted(tiers)})"
        ) from None


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
    tools: dict  # tool name -> callable(dict) -> str
    max_workers: int = 5
    # Remaining token budget for this run and its descendants (None = unlimited).
    cost_budget: int | None = None


def _exec_one(state: State, ctx: dict, feedback: str, deps: _Ctx, machine: Machine, depth: int):
    """Execute a state once → (output, sub_trace|None, reasoning|None, (in,out) tokens)."""
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
            cost_budget=deps.cost_budget,
            tools=deps.tools,
        )
        u = sub.usage or {}
        tin, tout = u.get("input_tokens", 0), u.get("output_tokens", 0)
        if sub.status != "done":
            # Parent must not continue as success with a missing/partial sub-result.
            raise CallFailed(sub.error or "sub-halted", sub.trace, tin, tout)
        return sub.result, sub.trace, None, (tin, tout)
    if state.kind == "tool":
        tool_input = {k: render(v, ctx) for k, v in (state.input or {}).items()}
        fn = deps.tools.get(state.tool)
        if fn is None:
            raise KeyError(f"tool: unknown tool {state.tool!r} (register it via run(tools=...))")
        return str(fn(tool_input)), None, None, (0, 0)
    tier = state.tier or machine.default_tier
    model = _model_for(state, machine, deps.tiers)
    params = deps.tier_params.get(tier)
    user = render(state.prompt, ctx) + (f"\n\n[Repair feedback] {feedback}" if feedback else "")
    temperature = 0.8 if state.sample else 0.4
    p = deps.llm.produce(
        model, _system(state), user, reason=state.reason, temperature=temperature, params=params
    )
    return p.text, None, p.reasoning, (p.input_tokens, p.output_tokens)


def _safe_exec(state, ctx, deps, machine, depth):
    """Execute one fan-out branch; a branch failure becomes a marker, not a crash."""
    try:
        return _exec_one(state, ctx, "", deps, machine, depth)
    except CallFailed as e:
        # Preserve nested trace + token usage from a sub-machine halt.
        return (f"[branch-error: {e.error}]", e.sub_trace, None, (e.input_tokens, e.output_tokens))
    except Exception as e:  # noqa: BLE001 — isolate the branch
        return (f"[branch-error: {e}]", None, None, (0, 0))


def _branch_contexts(state: State, ctx: dict) -> list[dict]:
    if state.sample:
        return [dict(ctx) for _ in range(state.sample)]
    m = _OVER_VAR.search(state.over or "")  # extract the path from "{{chunks}}"
    if not m:
        raise ValueError(f"over: invalid expression {state.over!r} (expected {{{{path}}}})")
    path = m.group(1)
    items = lookup(ctx, path)
    if items is None:
        raise KeyError(f"over: path {path!r} not found in context")
    if not isinstance(items, list):
        raise TypeError(f"over: path {path!r} is not a list (got {type(items).__name__})")
    out = []
    for i, item in enumerate(items):
        b = dict(ctx)
        b["item"], b["index"] = item, i
        out.append(b)
    return out


def _pick_otherwise(eligible: list[tuple[int, object]]) -> tuple[int, object] | None:
    for i, g in eligible:
        if g.when.strip().lower() == "otherwise":
            return i, g
    return None


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
    cost_budget: int | None = None,
    tools: dict | None = None,
) -> RunResult:
    if depth > MAX_CALL_DEPTH:
        return RunResult("halt", [], dict(context), error="call-depth-exceeded")
    deps = _Ctx(
        llm,
        tiers,
        judge_model,
        registry,
        tier_params or {},
        tools or {},
        max_workers,
        cost_budget,
    )
    ctx = dict(context)
    state_id = machine.entry
    trace: list[dict] = []
    steps = 0
    total_in = total_out = 0
    feedback = ""
    repair_left: dict[tuple[str, int], int] = {}

    def usage() -> dict:
        return {"input_tokens": total_in, "output_tokens": total_out}

    def spent() -> int:
        return total_in + total_out

    def remaining_budget() -> int | None:
        if cost_budget is None:
            return None
        return max(0, cost_budget - spent())

    while True:
        if steps >= machine.budget:
            return RunResult("halt", trace, ctx, error="budget-exhausted", usage=usage())
        if cost_budget is not None and spent() >= cost_budget:
            return RunResult("halt", trace, ctx, error="cost-exhausted", usage=usage())
        # Sub-runs inherit the *remaining* budget so parent+children share one pool.
        deps.cost_budget = remaining_budget()
        S = machine.states[state_id]
        step: dict = {"state": state_id, "tier": S.tier or machine.default_tier}

        # 1) EXECUTE (isolate failures: single → halt cleanly, branch → marker)
        judge_reasoning: str | None = None
        if S.is_fanout:
            try:
                branches = _branch_contexts(S, ctx)
            except Exception as e:  # noqa: BLE001 — bad over path / type
                return RunResult(
                    "halt",
                    trace,
                    ctx,
                    error=f"state-error: {e}",
                    at=state_id,
                    usage=usage(),
                )
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
                rs = [o[2] for o in outs if o[2]]
                judge_reasoning = "\n---\n".join(rs) if rs else None
            step_in = sum(o[3][0] for o in outs)
            step_out = sum(o[3][1] for o in outs)
        else:
            steps += 1
            try:
                out, sub, reasoning, (step_in, step_out) = _exec_one(
                    S, ctx, feedback, deps, machine, depth
                )
            except CallFailed as e:
                total_in += e.input_tokens
                total_out += e.output_tokens
                step["sub_trace"] = e.sub_trace
                if e.input_tokens or e.output_tokens:
                    step["cost"] = {
                        "input_tokens": e.input_tokens,
                        "output_tokens": e.output_tokens,
                    }
                step.update(step=steps, gate=None, policy="call-failed", to=None)
                trace.append(step)
                return RunResult(
                    "halt",
                    trace,
                    ctx,
                    error=f"call-failed: {e.error}",
                    at=state_id,
                    usage=usage(),
                )
            except RefusalError:
                return RunResult("halt", trace, ctx, error="refusal", at=state_id, usage=usage())
            except ProviderError as e:
                return RunResult(
                    "halt", trace, ctx, error=f"provider-error: {e}", at=state_id, usage=usage()
                )
            except Exception as e:  # noqa: BLE001 — surface as a clean halt, not a traceback
                return RunResult(
                    "halt", trace, ctx, error=f"state-error: {e}", at=state_id, usage=usage()
                )
            result = out
            judge_reasoning = reasoning
            step["output"] = out if isinstance(out, str) else fmt(out)
            if reasoning:
                step["reasoning"] = reasoning
            if sub is not None:
                step["sub_trace"] = sub
        feedback = ""
        total_in += step_in
        total_out += step_out
        if step_in or step_out:
            step["cost"] = {"input_tokens": step_in, "output_tokens": step_out}

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
            return RunResult(
                "halt", trace, ctx, error="no-gate-matched", at=state_id, usage=usage()
            )
        try:
            gi_local = deps.llm.judge(
                deps.judge_model,
                [g.when for _, g in eligible],
                fmt(result),
                ctx,
                reasoning=judge_reasoning,
            )
            gi_local = max(0, min(gi_local, len(eligible) - 1))  # trust nothing from the judge
            i, gate = eligible[gi_local]
        except JudgeUnparseable as e:
            # Soft-fallback only when an `otherwise` catch-all is eligible; else fail loud.
            step["judge_fallback"] = True
            step["judge_raw"] = str(e)[:200]
            catch = _pick_otherwise(eligible)
            if catch is None:
                step.update(step=steps, gate=None, policy="judge-unparseable", to=None)
                trace.append(step)
                return RunResult(
                    "halt",
                    trace,
                    ctx,
                    error="judge-unparseable",
                    at=state_id,
                    usage=usage(),
                )
            i, gate = catch
        step.update(step=steps, gate=gate.when, policy=gate.kind, to=gate.to)
        trace.append(step)

        # 4) TRANSITION
        if gate.kind == "fail":
            return RunResult("halt", trace, ctx, error="gate-fail", at=state_id, usage=usage())
        if gate.kind == "repair":
            repair_left[(state_id, i)] = repair_left.get((state_id, i), gate.repair) - 1
            feedback = f"The previous attempt did not satisfy: '{gate.when}'. Fix it."
        if gate.to == "END":
            rv = ctx.get(machine.result) if machine.result else result
            return RunResult("done", trace, ctx, result=rv, usage=usage())
        state_id = gate.to
