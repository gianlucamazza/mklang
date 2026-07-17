"""The mklang runtime: executes a Machine against an LLM (SPEC §6)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from .checkpoint import decode_repair, make_frame
from .errors import CallFailed, JudgeUnparseable, ProviderError, RefusalError
from .interpolate import fmt, lookup, render, resolve
from .model import Gate, Machine, State

MAX_CALL_DEPTH = 8
_OVER_VAR = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


@dataclass
class RunResult:
    status: str  # "done" | "halt" | "suspended"
    trace: list[dict]
    context: dict
    result: object = None
    error: str | None = None
    at: str | None = None
    usage: dict | None = None  # {"input_tokens": int, "output_tokens": int}
    frames: list[dict] | None = None  # checkpoint frames when status == "suspended"


class _Suspend(Exception):
    """Unwinds a suspendable run; each call level prepends its own frame."""

    def __init__(self, reason: str, frames: list[dict]):
        super().__init__(reason)
        self.reason = reason
        self.frames = frames


def _model_for(state: State, machine: Machine, tiers: dict) -> str:
    tier = state.tier or machine.default_tier
    try:
        return tiers[tier]
    except KeyError:
        raise KeyError(f"tier {tier!r} not configured (available: {sorted(tiers)})") from None


def _judge_model_for(state: State, machine: Machine, deps: "_Ctx") -> str:
    """Model that judges this state's gates (SPEC §2.1): the state's own tier by
    default, so a `reasoning` state's high-stakes gates are judged by the reasoning
    model — not silently downgraded. A configured `judge` override wins globally."""
    if deps.judge_override:
        return deps.judge_override
    return _model_for(state, machine, deps.tiers)


def _system(state: State) -> str:
    """Produce system message: structure + execution (see ``llm.prompts``)."""
    from .llm.prompts import build_produce_system

    return build_produce_system(state)


@dataclass
class _Ctx:
    """Shared execution dependencies threaded through the run."""

    llm: object
    tiers: dict
    # Global judge-model override (config `judge:`). None → judging follows each
    # state's tier (SPEC §2.1). See `_judge_model_for`.
    judge_override: str | None
    registry: dict
    tier_params: dict  # tier -> provider-specific params
    tools: dict  # tool name -> callable(dict) -> str
    hooks: dict  # hook name -> callable(ctx, output) -> bool
    max_workers: int = 5
    # Remaining token budget for this run and its descendants (None = unlimited).
    cost_budget: int | None = None
    # Budget exhaustion suspends (checkpoint frames) instead of halting.
    suspendable: bool = False
    # A fired escalate gate suspends for human input instead of just routing.
    escalate_suspend: bool = False
    # Optional live-observability callback (ADR 0015). Events mirror the trace;
    # terminal outcomes stay on RunResult. Must be thread-safe (fan-out branches
    # emit from worker threads) and is isolated: its exceptions never reach the run.
    on_event: object = None
    # Output anti-cutoff policy (ADR 0018): "report" annotates the trace;
    # "halt" aborts with state-error: output-truncated. Default report preserves
    # existing machine behavior while making cutoff observable.
    on_truncate: str = "report"
    # Per-value produce-prompt cap for {{…}} interpolation (ADR 0017). None →
    # interpolate.PROMPT_VALUE_CHARS; 0 → unlimited.
    prompt_value_chars: int | None = None
    # Cooperative cancellation, checked between states. The active provider
    # call is never interrupted mid-response.
    cancel_requested: object = None


def _emit(deps: "_Ctx", type_: str, machine: str, depth: int, **fields) -> None:
    if deps.on_event is None:
        return
    try:
        deps.on_event({"type": type_, "machine": machine, "depth": depth, **fields})
    except Exception:  # an observer must never affect the run
        pass


def _preview(value, limit: int = 200) -> str:
    text = value if isinstance(value, str) else fmt(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_otherwise(gate: Gate) -> bool:
    return gate.when.strip().lower() == "otherwise"


def _call_hook(gate: Gate, ctx: dict, result, hooks: dict) -> bool:
    fn = hooks.get(gate.hook)
    if fn is None:
        raise KeyError(f"hook: unknown hook {gate.hook!r} (register it via run(hooks=...))")
    return bool(fn(ctx, result))


def _select_gate(
    eligible: list[tuple[int, Gate]],
    result,
    ctx: dict,
    deps: _Ctx,
    judge_reasoning: str | None,
    judge_model: str,
) -> tuple[int, Gate, dict]:
    """Pick the first true gate (hooks / otherwise / fused LLM prose batch).

    `judge_model` is the model this state's prose gates are judged by (SPEC §2.1).
    Returns (gate_index_in_state, gate, step_annotations).
    """
    ann: dict = {}
    i = 0
    while i < len(eligible):
        gi, gate = eligible[i]
        if gate.hook and not _is_otherwise(gate):
            if _call_hook(gate, ctx, result, deps.hooks):
                ann["gate_via"] = "hook"
                ann["hook"] = gate.hook
                return gi, gate, ann
            i += 1
            continue
        if _is_otherwise(gate):
            ann["gate_via"] = "otherwise"
            return gi, gate, ann
        # Consecutive prose-only gates → one fused LLM judge call
        batch: list[tuple[int, Gate]] = []
        j = i
        while j < len(eligible):
            bj, bg = eligible[j]
            if bg.hook and not _is_otherwise(bg):
                break
            if _is_otherwise(bg):
                break
            batch.append((bj, bg))
            j += 1
        if not batch:
            i += 1
            continue
        try:
            verdict = deps.llm.judge(
                judge_model,
                [g.when for _, g in batch],
                fmt(result),
                ctx,
                reasoning=judge_reasoning,
            )
            # Adapters return the chosen index, optionally paired with the parse
            # method ("json" / "bare" / "last-number"). Mock/scripted judges return
            # a bare int (method unknown).
            if isinstance(verdict, tuple):
                local, parse_method = verdict
            else:
                local, parse_method = verdict, None
            # Adapters must return an index in [0, len(batch)); do not clamp here —
            # silent clamp would misroute with gate_via: llm and no anomaly flag.
            if not isinstance(local, int) or local < 0 or local >= len(batch):
                raise JudgeUnparseable(f"out-of-range choice {local!r} for n={len(batch)}")
            gi, gate = batch[local]
            ann["gate_via"] = "llm"
            ann["judge_model"] = judge_model
            # A non-JSON parse is anomaly-adjacent: trace it, but it is not a fallback.
            if parse_method and parse_method != "json":
                ann["judge_parse"] = parse_method
            return gi, gate, ann
        except JudgeUnparseable as e:
            ann["judge_fallback"] = True
            ann["judge_raw"] = str(e)[:200]
            # Prefer otherwise among the *full* remaining eligible list
            rest = eligible[i:]
            catch = _pick_otherwise(rest)
            if catch is None:
                raise
            gi, gate = catch
            ann["gate_via"] = "otherwise"
            return gi, gate, ann
    raise RuntimeError("no-gate-matched")


def _exec_one(
    state: State,
    ctx: dict,
    feedback: str,
    deps: _Ctx,
    machine: Machine,
    depth: int,
    resume: list[dict] | None = None,
):
    """Execute a state once → (output, sub_trace|None, reasoning|None, (in,out), meta).

    ``meta`` carries produce-side annotations (ADR 0018 truncation). Empty for
    tool/call states.
    """
    empty_meta: dict = {}
    if state.kind == "call":
        sub_input = {k: resolve(v, ctx) for k, v in (state.input or {}).items()}
        sub_machine = deps.registry.get(state.call)
        if sub_machine is None:
            raise KeyError(f"call: unknown machine {state.call!r}")
        sub = run(
            sub_machine,
            {**sub_machine.context, **sub_input},
            deps.registry,
            deps.llm,
            deps.tiers,
            deps.judge_override,
            depth=depth + 1,
            max_workers=deps.max_workers,
            tier_params=deps.tier_params,
            cost_budget=deps.cost_budget,
            tools=deps.tools,
            hooks=deps.hooks,
            suspendable=deps.suspendable,
            escalate_suspend=deps.escalate_suspend,
            resume=resume,
            on_event=deps.on_event,
            on_truncate=deps.on_truncate,
            prompt_value_chars=deps.prompt_value_chars,
            cancel_requested=deps.cancel_requested,
        )
        u = sub.usage or {}
        tin, tout = u.get("input_tokens", 0), u.get("output_tokens", 0)
        if sub.status != "done":
            # Parent must not continue as success with a missing/partial sub-result.
            raise CallFailed(sub.error or "sub-halted", sub.trace, tin, tout)
        return sub.result, sub.trace, None, (tin, tout), empty_meta
    if state.kind == "tool":
        tool_input = {k: resolve(v, ctx) for k, v in (state.input or {}).items()}
        fn = deps.tools.get(state.tool)
        if fn is None:
            raise KeyError(f"tool: unknown tool {state.tool!r} (register it via run(tools=...))")
        return str(fn(tool_input)), None, None, (0, 0), empty_meta
    tier = state.tier or machine.default_tier
    model = _model_for(state, machine, deps.tiers)
    params = deps.tier_params.get(tier)
    user = render(state.prompt, ctx, value_chars=deps.prompt_value_chars) + (
        f"\n\n[Repair feedback] {feedback}" if feedback else ""
    )
    temperature = 0.8 if state.sample else 0.4
    p = deps.llm.produce(
        model, _system(state), user, reason=state.reason, temperature=temperature, params=params
    )
    meta = {}
    if getattr(p, "truncated", False):
        meta["truncated"] = True
        if getattr(p, "finish_reason", None):
            meta["finish_reason"] = p.finish_reason
        if deps.on_truncate == "halt":
            raise ValueError("output-truncated")
        if state.parse == "list":
            # Partial JSON from a length stop is almost never a valid array —
            # fail with a clearer label than a generic parse error (ADR 0018).
            raise ValueError("parse-list-truncated")
    out = _parse_list(p.text) if state.parse == "list" else p.text
    return out, None, p.reasoning, (p.input_tokens, p.output_tokens), meta


def _parse_list(text: str) -> list:
    """`parse: list` (SPEC §4.10, 0.3): the produced text must be a JSON array
    (markdown fences tolerated); anything else halts the state (`state-error`)."""
    import json

    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        first_nl = body.find("\n")
        body = body[first_nl + 1 :] if first_nl != -1 else body
        body = body.strip()
    try:
        value = json.loads(body)
    except ValueError as e:
        raise ValueError(f"parse-list: output is not valid JSON ({e})") from e
    if not isinstance(value, list):
        raise ValueError(
            f"parse-list: output is JSON but not an array (got {type(value).__name__})"
        )
    return value


def _safe_exec(state, ctx, deps, machine, depth):
    """Execute one fan-out branch; a branch failure becomes a marker, not a crash."""
    try:
        # Branches never suspend: a budget-exhausted sub halts into a marker as
        # usual, and an escalate inside a branch just routes.
        out = _exec_one(
            state, ctx, "", replace(deps, suspendable=False, escalate_suspend=False), machine, depth
        )
    except CallFailed as e:
        # Preserve nested trace + token usage from a sub-machine halt.
        out = (
            f"[branch-error: {e.error}]",
            e.sub_trace,
            None,
            (e.input_tokens, e.output_tokens),
            {},
        )
    except Exception as e:  # isolate the branch
        out = (f"[branch-error: {e}]", None, None, (0, 0), {})
    _emit(
        deps,
        "branch-done",
        machine.name,
        depth,
        state=state.id,
        index=ctx.get("index"),
        tokens={"input_tokens": out[3][0], "output_tokens": out[3][1]},
    )
    return out


def _branch_contexts(state: State, ctx: dict) -> list[dict]:
    if state.sample:
        # Each sample branch sees its own `index` (0-based) so a prompt can say
        # "you are branch {{index}}, take a different approach" (Tree-of-Thought,
        # debate). `item` is only meaningful under `over`, so it is not set here.
        out = []
        for i in range(state.sample):
            b = dict(ctx)
            b["index"] = i
            out.append(b)
        return out
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


def _run_impl(
    machine: Machine,
    context: dict,
    registry: dict,
    llm,
    tiers: dict,
    judge: str | None = None,
    depth: int = 0,
    max_workers: int = 5,
    tier_params: dict | None = None,
    cost_budget: int | None = None,
    tools: dict | None = None,
    hooks: dict | None = None,
    suspendable: bool = False,
    escalate_suspend: bool = False,
    resume: list[dict] | None = None,
    on_event=None,
    on_truncate: str = "report",
    prompt_value_chars: int | None = None,
    cancel_requested=None,
) -> RunResult:
    if depth > MAX_CALL_DEPTH:
        return RunResult("halt", [], dict(context), error="call-depth-exceeded")
    if on_truncate not in ("report", "halt"):
        raise ValueError(f"on_truncate must be 'report' or 'halt', got {on_truncate!r}")
    deps = _Ctx(
        llm,
        tiers,
        judge,
        registry,
        tier_params or {},
        tools or {},
        hooks or {},
        max_workers,
        cost_budget,
        suspendable,
        escalate_suspend,
        on_event,
        on_truncate,
        prompt_value_chars,
        cancel_requested,
    )
    ctx = dict(context)
    state_id = machine.entry
    trace: list[dict] = []
    steps = 0
    total_in = total_out = 0
    feedback = ""
    repair_left: dict[tuple[str, int], int] = {}
    deeper: list[dict] | None = None  # frames to hand down into a call on the first iteration
    if resume:
        frame = resume[0]
        if frame.get("machine") != machine.name or frame.get("state") not in machine.states:
            return RunResult(
                "halt",
                [],
                dict(context),
                error=f"resume-mismatch: frame for {frame.get('machine')!r}"
                f"/{frame.get('state')!r} does not fit machine {machine.name!r}",
            )
        ctx = dict(frame["ctx"])
        state_id = frame["state"]
        trace = list(frame["trace"])
        steps = frame["steps"]
        total_in = frame["total_in"]
        total_out = frame["total_out"]
        feedback = frame["feedback"]
        repair_left = decode_repair(frame["repair_left"])
        deeper = list(resume[1:]) or None

    def usage() -> dict:
        return {"input_tokens": total_in, "output_tokens": total_out}

    def spent() -> int:
        return total_in + total_out

    def remaining_budget() -> int | None:
        if cost_budget is None:
            return None
        return max(0, cost_budget - spent())

    def snapshot(at_steps: int | None = None) -> dict:
        return make_frame(
            machine.name,
            state_id,
            ctx,
            steps if at_steps is None else at_steps,
            total_in,
            total_out,
            feedback,
            repair_left,
            trace,
        )

    def suspended(reason: str) -> RunResult:
        """Checkpoint this level; nested levels unwind via _Suspend, depth 0 returns."""
        if depth:
            raise _Suspend(reason, [snapshot()])
        return RunResult(
            "suspended",
            trace,
            ctx,
            error=reason,
            at=state_id,
            usage=usage(),
            frames=[snapshot()],
        )

    def suspend_or_halt(reason: str) -> RunResult:
        """Loop-top budget exhaustion: checkpoint frames when suspendable, else halt."""
        if deps.suspendable:
            return suspended(reason)
        return RunResult("halt", trace, ctx, error=reason, usage=usage())

    def record(step: dict) -> None:
        """Append to the trace and mirror it as a live event (ADR 0015)."""
        trace.append(step)
        fields = {
            "state": step["state"],
            "step": step.get("step"),
            "gate": step.get("gate"),
            "policy": step.get("policy"),
            "to": step.get("to"),
        }
        if "output" in step:
            fields["output"] = _preview(step["output"])
        if "branches" in step:
            fields["branches"] = len(step["branches"])
        if "cost" in step:
            fields["tokens"] = step["cost"]
        # Surface output anti-cutoff to live observers (console tree, MCP logs).
        if step.get("truncated"):
            fields["truncated"] = True
            if step.get("finish_reason"):
                fields["finish_reason"] = step["finish_reason"]
        _emit(deps, "state-done", machine.name, depth, **fields)

    _emit(deps, "run-start", machine.name, depth, entry=state_id, resumed=bool(resume))
    while True:
        if cancel_requested is not None:
            try:
                cancelled = bool(cancel_requested())
            except Exception:
                cancelled = False
            if cancelled:
                return RunResult("halt", trace, ctx, error="cancelled", at=state_id, usage=usage())
        if steps >= machine.budget:
            return suspend_or_halt("budget-exhausted")
        if cost_budget is not None and spent() >= cost_budget:
            return suspend_or_halt("cost-exhausted")
        # Sub-runs inherit the *remaining* budget so parent+children share one pool.
        deps.cost_budget = remaining_budget()
        S = machine.states[state_id]
        sub_resume, deeper = deeper, None  # descend into the suspended call once, then clear
        if sub_resume is not None and S.kind != "call":
            return RunResult(
                "halt",
                trace,
                ctx,
                error=f"resume-mismatch: state {state_id!r} is not a call",
                at=state_id,
                usage=usage(),
            )
        step: dict = {"state": state_id, "tier": S.tier or machine.default_tier}
        _emit(
            deps,
            "state-start",
            machine.name,
            depth,
            state=state_id,
            step=steps + 1,
            kind=S.kind,
            tier=step["tier"],
        )

        # 1) EXECUTE (isolate failures: single → halt cleanly, branch → marker)
        judge_reasoning: str | None = None
        if S.is_fanout:
            try:
                branches = _branch_contexts(S, ctx)
            except Exception as e:  # bad over path / type
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
            # Any branch that reported produce truncation annotates the parent step.
            trunc_metas = [o[4] for o in outs if (o[4] or {}).get("truncated")]
            if trunc_metas:
                step["truncated"] = True
                # First branch's finish_reason is enough signal for the parent step.
                fr = trunc_metas[0].get("finish_reason")
                if fr:
                    step["finish_reason"] = fr
        else:
            steps += 1
            try:
                out, sub, reasoning, (step_in, step_out), meta = _exec_one(
                    S, ctx, feedback, deps, machine, depth, resume=sub_resume
                )
            except _Suspend as s:
                # A sub-call suspended: prepend this level's loop-top frame and keep unwinding.
                s.frames.insert(0, snapshot(at_steps=steps - 1))
                if depth:
                    raise
                return RunResult(
                    "suspended",
                    trace,
                    ctx,
                    error=s.reason,
                    at=s.frames[-1]["state"],
                    usage=usage(),
                    frames=s.frames,
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
                record(step)
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
            except Exception as e:  # surface as a clean halt, not a traceback
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
            if meta.get("truncated"):
                step["truncated"] = True
                if meta.get("finish_reason"):
                    step["finish_reason"] = meta["finish_reason"]
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

        # 3) JUDGE — hooks (host bool) then otherwise then fused LLM prose (SPEC §5)
        eligible = [
            (i, g)
            for i, g in enumerate(S.gates)
            if not (g.kind == "repair" and repair_left.get((state_id, i), g.repair) == 0)
        ]
        if not eligible:  # every gate was a repair with an exhausted budget
            step.update(step=steps, gate=None, policy="no-gate-matched", to=None)
            record(step)
            return RunResult(
                "halt", trace, ctx, error="no-gate-matched", at=state_id, usage=usage()
            )
        try:
            judge_model = _judge_model_for(S, machine, deps)
            i, gate, gann = _select_gate(eligible, result, ctx, deps, judge_reasoning, judge_model)
            step.update(gann)
        except JudgeUnparseable:
            step.update(step=steps, gate=None, policy="judge-unparseable", to=None)
            if "judge_fallback" not in step:
                step["judge_fallback"] = True
            record(step)
            return RunResult(
                "halt",
                trace,
                ctx,
                error="judge-unparseable",
                at=state_id,
                usage=usage(),
            )
        except RuntimeError as e:
            if str(e) == "no-gate-matched":
                step.update(step=steps, gate=None, policy="no-gate-matched", to=None)
                record(step)
                return RunResult(
                    "halt", trace, ctx, error="no-gate-matched", at=state_id, usage=usage()
                )
            return RunResult(
                "halt", trace, ctx, error=f"state-error: {e}", at=state_id, usage=usage()
            )
        except Exception as e:  # missing hook / host error
            return RunResult(
                "halt", trace, ctx, error=f"state-error: {e}", at=state_id, usage=usage()
            )
        step.update(step=steps, gate=gate.when, policy=gate.kind, to=gate.to)
        record(step)

        # 4) TRANSITION
        if gate.kind == "fail":
            return RunResult("halt", trace, ctx, error="gate-fail", at=state_id, usage=usage())
        if gate.kind == "repair":
            repair_left[(state_id, i)] = repair_left.get((state_id, i), gate.repair) - 1
            feedback = f"The previous attempt did not satisfy: '{gate.when}'. Fix it."
        if gate.kind == "escalate" and deps.escalate_suspend and gate.to != "END":
            # HITL: pause before the handler runs; a resume can drop the human
            # reply into ctx so the handler state sees it (ADR 0008).
            state_id = gate.to
            return suspended("escalated")
        if gate.to == "END":
            rv = ctx.get(machine.result) if machine.result else result
            return RunResult("done", trace, ctx, result=rv, usage=usage())
        state_id = gate.to


def run(
    machine: Machine,
    context: dict,
    registry: dict,
    llm,
    tiers: dict,
    judge: str | None = None,
    depth: int = 0,
    max_workers: int = 5,
    tier_params: dict | None = None,
    cost_budget: int | None = None,
    tools: dict | None = None,
    hooks: dict | None = None,
    suspendable: bool = False,
    escalate_suspend: bool = False,
    resume: list[dict] | None = None,
    on_event=None,
    on_truncate: str = "report",
    prompt_value_chars: int | None = None,
    cancel_requested=None,
) -> RunResult:
    """Run a machine and emit one additive terminal event for every outcome.

    ``cancel_requested`` is cooperative and observed between states. Existing
    callers that omit it retain identical semantics.
    """
    result = _run_impl(
        machine,
        context,
        registry,
        llm,
        tiers,
        judge,
        depth,
        max_workers,
        tier_params,
        cost_budget,
        tools,
        hooks,
        suspendable,
        escalate_suspend,
        resume,
        on_event,
        on_truncate,
        prompt_value_chars,
        cancel_requested,
    )
    if on_event is not None:
        try:
            on_event(
                {
                    "type": "run-finished",
                    "machine": machine.name,
                    "depth": depth,
                    "status": result.status,
                    "error": result.error,
                    "at": result.at,
                    "tokens": result.usage or {"input_tokens": 0, "output_tokens": 0},
                }
            )
        except Exception:
            pass
    return result
