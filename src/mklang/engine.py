"""The mklang runtime: executes a Machine against an LLM (SPEC §6)."""

from __future__ import annotations

import contextlib
import inspect
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

from .checkpoint import decode_repair, make_frame
from .controlflow import FLOW_POLICIES, is_effectful, machine_touches_tools
from .errors import CallFailed, JudgeUnparseable, ProviderError, RefusalError
from .interpolate import fmt, lookup, render, render_delimited, resolve
from .llm.base import LLM
from .model import Gate, Machine, State

MAX_CALL_DEPTH = 8
_OVER_VAR = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

# (output, sub_trace|None, reasoning|None, (in,out), meta)
ExecOut = tuple[object, list[dict] | None, str | None, tuple[int, int], dict]
Eligible = list[tuple[int, Gate]]


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


def _model_for(state: State, machine: Machine, tiers: dict[str, str]) -> str:
    tier = state.tier or machine.default_tier
    try:
        return tiers[tier]
    except KeyError:
        raise KeyError(f"tier {tier!r} not configured (available: {sorted(tiers)})") from None


def _judge_model_for(state: State, machine: Machine, deps: _Ctx) -> str:
    """Model that judges this state's gates (SPEC §2.1): the state's own tier by
    default, so a `reasoning` state's high-stakes gates are judged by the reasoning
    model — not silently downgraded. A configured `judge` override wins globally."""
    if deps.judge_override:
        return deps.judge_override
    return _model_for(state, machine, deps.tiers)


def _system(state: State, data_nonce: str | None = None) -> str:
    """Produce system message: structure + execution (see ``llm.prompts``)."""
    from .llm.prompts import build_produce_system

    return build_produce_system(state, data_nonce=data_nonce)


@dataclass
class _Ctx:
    """Shared execution dependencies threaded through the run."""

    llm: LLM
    tiers: dict[str, str]
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
    on_event: Callable[[dict], None] | None = None
    # Output anti-cutoff policy (ADR 0018): "report" annotates the trace;
    # "halt" aborts with state-error: output-truncated. Default report preserves
    # existing machine behavior while making cutoff observable.
    on_truncate: str = "report"
    # Per-value produce-prompt cap for {{…}} interpolation (ADR 0017). None →
    # interpolate.PROMPT_VALUE_CHARS; 0 → unlimited.
    prompt_value_chars: int | None = None
    # Cooperative cancellation, checked between states. The active provider
    # call is never interrupted mid-response.
    cancel_requested: Callable[[], object] | None = None
    # Untrusted-context delimiting (SPEC §6 / ADR 0025): fence tainted
    # interpolations in produce prompts. Off only for debugging/comparison.
    delimit: bool = True
    # Control-flow taint (SPEC §6 / ADR 0030): what to do when a decision made by
    # a judge reading external data reaches an effectful tool state. "report"
    # annotates the trace (default — the propagation rule is normative, the
    # enforcement policy is the host's); "halt" refuses the effect.
    on_untrusted_flow: str = "report"
    # Host classification of tool names ("read" / "effect"), overriding
    # controlflow.TOOL_EFFECTS. Unlisted tools stay effectful by default.
    tool_effects: dict[str, str] = field(default_factory=dict)


def _emit(deps: _Ctx, type_: str, machine: str, depth: int, **fields: object) -> None:
    if deps.on_event is None:
        return
    # An observer must never affect the run.
    with contextlib.suppress(Exception):
        deps.on_event({"type": type_, "machine": machine, "depth": depth, **fields})


def _preview(value: object, limit: int = 200) -> str:
    text = value if isinstance(value, str) else fmt(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_otherwise(gate: Gate) -> bool:
    return gate.when.strip().lower() == "otherwise"


def _call_hook(gate: Gate, ctx: dict, result: object, hooks: dict) -> bool:
    from .hooks import resolve_hook

    fn = resolve_hook(gate.hook, hooks)
    if fn is None:
        # LookupError, not KeyError: KeyError's str() re-quotes the whole message,
        # so the halt reason would read state-error: "hook: unknown hook 'x' …".
        raise LookupError(f"hook: unknown hook {gate.hook!r} (register it via run(hooks=...))")
    return bool(fn(ctx, result))


def _collect_prose_batch(eligible: Eligible, start: int) -> list[tuple[int, Gate]]:
    """Consecutive prose-only gates starting at ``start`` (stop at hook/otherwise)."""
    batch: list[tuple[int, Gate]] = []
    j = start
    while j < len(eligible):
        bj, bg = eligible[j]
        if bg.hook and not _is_otherwise(bg):
            break
        if _is_otherwise(bg):
            break
        batch.append((bj, bg))
        j += 1
    return batch


def _judge_supports_none(llm: object) -> bool:
    """True when ``llm.judge`` accepts the ``allow_none`` keyword (SPEC §5).

    Inspect the signature instead of calling with the kwarg and catching
    ``TypeError``: a TypeError raised *inside* a modern adapter (bug, bad
    argument) must not be misread as "legacy forced-choice adapter".
    ``**kwargs`` adapters count as supporting the option.
    """
    try:
        params = inspect.signature(llm.judge).parameters  # type: ignore[attr-defined]
    except (TypeError, ValueError):
        return False
    if "allow_none" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def _human_confirmed(frame: dict, ctx: dict) -> bool:
    """HITL confirmation at resume: a ``human.reply`` injected for THIS suspension.

    Two things must hold, and each rules out a way the confirmation could be
    forged by accident (ADR 0008 / ADR 0030):

    - the frame records a `human*` path among the values this resume injected
      (`resume_injected`, written by `checkpoint.taint_frame`). A reply left in
      the blackboard by an earlier HITL cycle is not a confirmation of a decision
      taken after it; a frame with no record at all — pre-0030 checkpoint, or a
      resume that injected nothing — confirms nothing;
    - the value is actually a reply. The bare presence of a `human` key (author
      context schema, empty placeholder, unrelated payload) is not one.
    """
    injected = frame.get("resume_injected")
    if not isinstance(injected, list):
        return False
    if not any(str(k).split(".")[0] == "human" for k in injected):
        return False
    human = ctx.get("human")
    return isinstance(human, dict) and "reply" in human


def _call_judge(
    deps: _Ctx,
    judge_model: str,
    conditions: list[str],
    result: object,
    ctx: dict,
    judge_reasoning: str | None,
) -> tuple[object, bool]:
    """Judge a condition batch, asking for the *none of the above* option (SPEC §5).

    Returns ``(verdict, total)``. Adapters written before ``allow_none`` (third-party
    provider plugins) keep working as a forced choice; ``total`` is False for them so
    the step can be traced as judged under the older, non-total protocol.
    """
    if _judge_supports_none(deps.llm):
        return (
            deps.llm.judge(
                judge_model,
                conditions,
                fmt(result),
                ctx,
                reasoning=judge_reasoning,
                allow_none=True,
            ),
            True,
        )
    verdict = deps.llm.judge(
        judge_model,
        conditions,
        fmt(result),
        ctx,
        reasoning=judge_reasoning,
    )
    return verdict, False


def _judge_prose_batch(
    batch: list[tuple[int, Gate]],
    eligible: Eligible,
    start: int,
    result: object,
    ctx: dict,
    deps: _Ctx,
    judge_reasoning: str | None,
    judge_model: str,
    ann: dict,
) -> tuple[int | None, Gate | None, dict, tuple[int, int]]:
    """Fused LLM judge over a prose batch (SPEC §5).

    Returns ``(gate_index, gate, ann, usage)``; a ``None`` gate means the judge
    answered *none of the above* — every condition in the batch is false, so the
    caller resumes the scan at the gate after the batch. `JudgeUnparseable` still
    soft-falls back to an eligible `otherwise`.
    """
    try:
        verdict, total = _call_judge(
            deps, judge_model, [g.when for _, g in batch], result, ctx, judge_reasoning
        )
        # Adapters return the chosen index, optionally paired with the parse
        # method ("json" / "bare" / "last-number"). Mock/scripted judges return
        # a bare int (method unknown).
        if isinstance(verdict, tuple):
            local, parse_method = verdict[:2]
        else:
            local, parse_method = verdict, None
        # Adapters must return an index in [0, len(batch)] — the last value is the
        # *none of the above* option, and only when it was offered. Do not clamp:
        # a silent clamp would misroute with gate_via: llm and no anomaly flag.
        top = len(batch) if total else len(batch) - 1
        if not isinstance(local, int) or local < 0 or local > top:
            raise JudgeUnparseable(f"out-of-range choice {local!r} for n={top + 1}")
        usage = getattr(deps.llm, "last_judge_usage", (0, 0))
        cost = (int(usage[0] or 0), int(usage[1] or 0))
        if local == len(batch):  # no condition in this batch holds — keep scanning
            ann["judge_model"] = judge_model
            ann["judge_none"] = int(ann.get("judge_none", 0)) + 1
            if parse_method and parse_method != "json":
                ann["judge_parse"] = parse_method
            return None, None, ann, cost
        gi, gate = batch[local]
        ann["gate_via"] = "llm"
        ann["judge_model"] = judge_model
        if not total:
            # Forced choice: this verdict cannot express "none of these hold".
            ann["judge_forced_choice"] = True
        # A non-JSON parse is anomaly-adjacent: trace it, but it is not a fallback.
        if parse_method and parse_method != "json":
            ann["judge_parse"] = parse_method
        return gi, gate, ann, cost
    except JudgeUnparseable as e:
        ann["judge_fallback"] = True
        ann["judge_raw"] = str(e)[:200]
        # Prefer otherwise among the *full* remaining eligible list
        rest = eligible[start:]
        catch = _pick_otherwise(rest)
        if catch is None:
            raise
        gi, gate = catch
        ann["gate_via"] = "otherwise"
        return gi, gate, ann, (0, 0)


def _select_gate(
    eligible: Eligible,
    result: object,
    ctx: dict,
    deps: _Ctx,
    judge_reasoning: str | None,
    judge_model: str,
) -> tuple[int, Gate, dict, tuple[int, int]]:
    """Pick the first true gate (hooks / otherwise / fused LLM prose batch).

    One left-to-right scan over the eligible gates, exactly as SPEC §5 defines it:
    a hook that returns False and a prose batch the judge rejects both fall
    through to the next gate. Reaching the end without a true gate is
    `no-gate-matched` — the partial-transition halt a catch-all gate prevents.

    `judge_model` is the model this state's prose gates are judged by (SPEC §2.1).
    Returns (gate_index_in_state, gate, step_annotations, judge_usage).
    """
    ann: dict = {}
    spent_in = spent_out = 0
    i = 0
    while i < len(eligible):
        gi, gate = eligible[i]
        if gate.hook and not _is_otherwise(gate):
            if _call_hook(gate, ctx, result, deps.hooks):
                ann["gate_via"] = "hook"
                ann["hook"] = gate.hook
                return gi, gate, ann, (spent_in, spent_out)
            i += 1
            continue
        if _is_otherwise(gate):
            ann["gate_via"] = "otherwise"
            return gi, gate, ann, (spent_in, spent_out)
        batch = _collect_prose_batch(eligible, i)
        if not batch:
            i += 1
            continue
        bi, bgate, ann, (batch_in, batch_out) = _judge_prose_batch(
            batch, eligible, i, result, ctx, deps, judge_reasoning, judge_model, ann
        )
        spent_in += batch_in
        spent_out += batch_out
        if bgate is None:  # judge: none of these conditions is true — keep scanning
            i += len(batch)
            continue
        assert bi is not None
        return bi, bgate, ann, (spent_in, spent_out)
    raise RuntimeError("no-gate-matched")


def _exec_call(
    state: State,
    ctx: dict,
    deps: _Ctx,
    machine: Machine,
    depth: int,
    resume: list[dict] | None,
    tainted: set[str],
    flow_tainted: bool = False,
) -> ExecOut:
    sub_input = {k: resolve(v, ctx) for k, v in (state.input or {}).items()}
    # An input key is trusted in the sub-run unless its value interpolates
    # a tainted key here; the sub-run's own provenance rule handles the rest.
    trusted_inputs = {k for k, v in (state.input or {}).items() if not _refs_tainted(v, tainted)}
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
        delimit=deps.delimit,
        trusted_keys=trusted_inputs,
        on_untrusted_flow=deps.on_untrusted_flow,
        tool_effects=deps.tool_effects,
        # A tainted decision is not laundered by one level of indirection: the
        # sub-run inherits it, so the guard fires on the effect the sub-machine
        # performs (SPEC §6 / ADR 0030). The sub-run's own confirmation does not
        # travel back up — it clears the sub-machine's decision chain, not ours.
        flow_tainted=flow_tainted,
    )
    u = sub.usage or {}
    tin, tout = u.get("input_tokens", 0), u.get("output_tokens", 0)
    if sub.status != "done":
        # Parent must not continue as success with a missing/partial sub-result.
        raise CallFailed(sub.error or "sub-halted", sub.trace, tin, tout)
    return sub.result, sub.trace, None, (tin, tout), {}


def _exec_tool(state: State, ctx: dict, deps: _Ctx) -> ExecOut:
    tool_input = {k: resolve(v, ctx) for k, v in (state.input or {}).items()}
    fn = deps.tools.get(state.tool)
    if fn is None:
        raise KeyError(f"tool: unknown tool {state.tool!r} (register it via run(tools=...))")
    return str(fn(tool_input)), None, None, (0, 0), {}


def _exec_produce(
    state: State,
    ctx: dict,
    feedback: str,
    deps: _Ctx,
    machine: Machine,
    tainted: set[str],
) -> ExecOut:
    tier = state.tier or machine.default_tier
    model = _model_for(state, machine, deps.tiers)
    params = deps.tier_params.get(tier)
    if deps.delimit:
        prompt, nonce = render_delimited(
            state.prompt, ctx, value_chars=deps.prompt_value_chars, tainted=tainted
        )
    else:
        prompt, nonce = render(state.prompt, ctx, value_chars=deps.prompt_value_chars), None
    user = prompt + (f"\n\n[Repair feedback] {feedback}" if feedback else "")
    temperature = 0.8 if state.sample else 0.4
    p = deps.llm.produce(
        model,
        _system(state, nonce),
        user,
        reason=state.reason,
        temperature=temperature,
        params=params,
    )
    meta: dict = {}
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


def _exec_one(
    state: State,
    ctx: dict,
    feedback: str,
    deps: _Ctx,
    machine: Machine,
    depth: int,
    resume: list[dict] | None = None,
    tainted: set[str] | None = None,
    flow_tainted: bool = False,
) -> ExecOut:
    """Execute a state once → (output, sub_trace|None, reasoning|None, (in,out), meta).

    ``meta`` carries produce-side annotations (ADR 0018 truncation). Empty for
    tool/call states. ``flow_tainted`` is only consumed by `call`: it hands the
    run's control-flow taint to the sub-run (ADR 0030).
    """
    tainted = tainted if tainted is not None else set()
    if state.kind == "call":
        return _exec_call(state, ctx, deps, machine, depth, resume, tainted, flow_tainted)
    if state.kind == "tool":
        return _exec_tool(state, ctx, deps)
    return _exec_produce(state, ctx, feedback, deps, machine, tainted)


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


def _safe_exec(
    state: State,
    ctx: dict,
    deps: _Ctx,
    machine: Machine,
    depth: int,
    tainted: set[str] | None = None,
    flow_tainted: bool = False,
) -> ExecOut:
    """Execute one fan-out branch; a branch failure becomes a marker, not a crash."""
    try:
        # Branches never suspend: a budget-exhausted sub halts into a marker as
        # usual, and an escalate inside a branch just routes.
        out = _exec_one(
            state,
            ctx,
            "",
            replace(deps, suspendable=False, escalate_suspend=False),
            machine,
            depth,
            tainted=tainted,
            flow_tainted=flow_tainted,
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


def _pick_otherwise(eligible: Eligible) -> tuple[int, Gate] | None:
    for i, g in eligible:
        if g.when.strip().lower() == "otherwise":
            return i, g
    return None


def _refs_tainted(value: object, tainted: set[str]) -> bool:
    """True when an `input:` value interpolates any tainted top-level key.

    Non-string YAML values are author literals — trusted by construction."""
    if not isinstance(value, str) or not tainted:
        return False
    return any(m.group(1).split(".")[0] in tainted for m in _OVER_VAR.finditer(value))


def _initial_taint(machine: Machine, ctx: dict, trusted_keys: set[str] | None) -> set[str]:
    """Top-level keys whose values differ from the authoring literal (SPEC §6)."""
    return {k for k in ctx if machine.context.get(k) != ctx[k]} - set(trusted_keys or ())


def _is_external_deposit(state: State, external: set[str], deps: _Ctx) -> bool:
    """True when this state's output carries data from OUTSIDE the run (SPEC §6).

    `external` is a strict subset of `tainted`. Every deposit is tainted — produce
    output is oracle-derived even from author literals — so the tainted set cannot
    distinguish "a model wrote this" from "an outsider wrote this", and a rule
    keyed on it would apply to every prose gate in every machine. External taint
    is the narrower question control flow actually cares about: did anything a
    third party controls reach this value?

    - `tool:` observations are external, always.
    - a `call` result is external if any input carries external data, or if the
      sub-machine can reach a tool state at all (`machine_touches_tools`).
    - a generative output is external if its prompt, its `over:` source, or its
      fan-out item interpolated something external.
    """
    if state.kind == "tool":
        return True
    if state.kind == "call":
        if any(_refs_tainted(v, external) for v in (state.input or {}).values()):
            return True
        return machine_touches_tools(deps.registry.get(state.call or ""), deps.registry)
    return _refs_tainted(state.prompt, external) or _refs_tainted(state.over, external)


def _deposit(ctx: dict, tainted: set[str], state: State, result: object) -> None:
    """Write state output into the blackboard and mark it tainted (SPEC §11)."""
    if state.accumulate:
        prev = ctx.get(state.output, [])
        if not isinstance(prev, list):
            prev = [prev]
        ctx[state.output] = [*prev, result]
    else:
        ctx[state.output] = result
    tainted.add(state.output)


def _apply_gate_transition(
    gate: Gate,
    gate_index: int,
    state_id: str,
    *,
    repair_left: dict[tuple[str, int], int],
) -> tuple[str | None, str, str | None]:
    """Map a selected gate to (next_state_id | END | None, feedback, halt_error).

    When halt_error is set, next_state is None and the run should halt.
    HITL escalate-suspend is handled by the caller (needs deps.escalate_suspend).
    """
    if gate.kind == "fail":
        return None, "", "gate-fail"
    to = gate.to
    if to is None:
        return None, "", "state-error: gate-missing-to"
    feedback = ""
    if gate.kind == "repair":
        if gate.repair is None:
            return None, "", "state-error: repair-missing-budget"
        repair_left[(state_id, gate_index)] = (
            repair_left.get((state_id, gate_index), gate.repair) - 1
        )
        feedback = f"The previous attempt did not satisfy: '{gate.when}'. Fix it."
    return to, feedback, None


def _fanout_branch_taint(state: State, tainted: set[str]) -> set[str]:
    branch_tainted = set(tainted)
    if state.over:
        m_over = _OVER_VAR.search(state.over)
        if m_over and m_over.group(1).split(".")[0] in tainted:
            branch_tainted.add("item")  # `index` stays trusted
    return branch_tainted


def _fanout_branch_previews(outs: list[ExecOut]) -> list[str]:
    return [o[0] if isinstance(o[0], str) else fmt(o[0]) for o in outs]


def _fanout_reasoning(state: State, outs: list[ExecOut], step_fields: dict) -> str | None:
    if not state.reason:
        return None
    step_fields["reasonings"] = [o[2] for o in outs]
    rs = [o[2] for o in outs if o[2]]
    return "\n---\n".join(rs) if rs else None


def _fanout_truncation(outs: list[ExecOut], step_fields: dict) -> None:
    trunc_metas = [o[4] for o in outs if (o[4] or {}).get("truncated")]
    if not trunc_metas:
        return
    step_fields["truncated"] = True
    fr = trunc_metas[0].get("finish_reason")
    if fr:
        step_fields["finish_reason"] = fr


def _reduce_fanout(state: State, outs: list[ExecOut]) -> tuple[object, str | None, int, int, dict]:
    """Collapse branch ExecOuts into (result, judge_reasoning, step_in, step_out, fields)."""
    result: object = [o[0] for o in outs]
    step_fields: dict = {"branches": _fanout_branch_previews(outs)}
    subs = [o[1] for o in outs if o[1] is not None]
    if subs:
        step_fields["sub_trace"] = subs
    judge_reasoning = _fanout_reasoning(state, outs, step_fields)
    step_in = sum(o[3][0] for o in outs)
    step_out = sum(o[3][1] for o in outs)
    _fanout_truncation(outs, step_fields)
    return result, judge_reasoning, step_in, step_out, step_fields


def _execute_fanout(
    state: State,
    state_id: str,
    ctx: dict,
    deps: _Ctx,
    machine: Machine,
    depth: int,
    tainted: set[str],
    steps: int,
    trace: list[dict],
    usage_tokens: tuple[int, int],
    flow_tainted: bool = False,
) -> tuple[object, str | None, int, int, int, dict] | RunResult:
    """Run a sample/over fan-out.

    Returns (result, judge_reasoning, step_in, step_out, steps, step_fields)
    or a halt RunResult on branch-setup failure.
    """
    total_in, total_out = usage_tokens
    try:
        branches = _branch_contexts(state, ctx)
    except Exception as e:  # bad over path / type
        return RunResult(
            "halt",
            trace,
            ctx,
            error=f"state-error: {e}",
            at=state_id,
            usage={"input_tokens": total_in, "output_tokens": total_out},
        )
    # Fan-out: step count is max(1, n_branches) — see SPEC fan-out charging.
    new_steps = steps + max(1, len(branches))
    branch_tainted = _fanout_branch_taint(state, tainted)
    if branches:
        with ThreadPoolExecutor(max_workers=deps.max_workers) as ex:
            branch_budget = None
            if deps.cost_budget is not None:
                branch_budget = max(1, deps.cost_budget // len(branches))
            outs = list(
                ex.map(
                    lambda b: _safe_exec(
                        state,
                        b,
                        replace(deps, cost_budget=branch_budget),
                        machine,
                        depth,
                        branch_tainted,
                        flow_tainted,
                    ),
                    branches,
                )
            )
    else:
        outs = []
    result, judge_reasoning, step_in, step_out, step_fields = _reduce_fanout(state, outs)
    return result, judge_reasoning, step_in, step_out, new_steps, step_fields


class _Runner:
    """Mutable run state and the main loop (SPEC §6). Public API remains ``run``."""

    def __init__(
        self,
        machine: Machine,
        context: dict,
        registry: dict,
        llm: LLM,
        tiers: dict[str, str],
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
        on_event: Callable[[dict], None] | None = None,
        on_truncate: str = "report",
        prompt_value_chars: int | None = None,
        cancel_requested: Callable[[], object] | None = None,
        delimit: bool = True,
        trusted_keys: set[str] | None = None,
        on_untrusted_flow: str = "report",
        tool_effects: dict[str, str] | None = None,
        flow_tainted: bool = False,
    ) -> None:
        self.machine = machine
        self.depth = depth
        self.cost_budget = cost_budget
        self.cancel_requested = cancel_requested
        self._resume_arg = resume
        # Annotated once so both the depth-exceeded early path and the normal path
        # share the same attribute types (mypy no-redef / var-annotated).
        self.ctx: dict = dict(context)
        self.tainted: set[str] = set()
        # Control-flow taint (SPEC §6 / ADR 0030): `external` ⊆ `tainted` holds the
        # keys carrying data from outside the run; `flow_tainted` records that the
        # transition which brought us here was chosen by a judge reading such data,
        # with no hook or human confirmation since. A sub-run starts from the
        # caller's flag: `call:` is not a laundering step. A checkpoint frame, when
        # one applies, overrides it in `_from_resume`.
        self.external: set[str] = set()
        self.flow_tainted: bool = flow_tainted
        self.state_id: str = machine.entry
        self.trace: list[dict] = []
        self.steps: int = 0
        self.total_in: int = 0
        self.total_out: int = 0
        self.feedback: str = ""
        self.repair_left: dict[tuple[str, int], int] = {}
        self.deeper: list[dict] | None = None
        self._init_error: RunResult | None = None
        # Preflight matches the historical _run_impl order: depth / on_truncate
        # before building deps or applying a resume frame.
        if depth > MAX_CALL_DEPTH:
            self._init_error = RunResult("halt", [], dict(context), error="call-depth-exceeded")
            self.deps = _Ctx(llm, tiers, judge, registry, {}, {}, {})
            return
        if on_truncate not in ("report", "halt"):
            raise ValueError(f"on_truncate must be 'report' or 'halt', got {on_truncate!r}")
        if on_untrusted_flow not in FLOW_POLICIES:
            raise ValueError(
                f"on_untrusted_flow must be one of {FLOW_POLICIES}, got {on_untrusted_flow!r}"
            )
        self.deps = _Ctx(
            llm,
            tiers,
            judge,
            registry,
            tier_params=tier_params or {},
            tools=tools or {},
            hooks=hooks or {},
            max_workers=max_workers,
            cost_budget=cost_budget,
            suspendable=suspendable,
            escalate_suspend=escalate_suspend,
            on_event=on_event,
            on_truncate=on_truncate,
            prompt_value_chars=prompt_value_chars,
            cancel_requested=cancel_requested,
            delimit=delimit,
            on_untrusted_flow=on_untrusted_flow,
            tool_effects=dict(tool_effects or {}),
        )
        # Provenance taint (SPEC §6 / ADR 0025): a top-level key is trusted iff its
        # value is still the author's `.mkl` literal; host-supplied or host-overridden
        # values are untrusted unless the embedder vouches via `trusted_keys`.
        self.tainted = _initial_taint(machine, self.ctx, trusted_keys)
        # Everything the host supplied came from outside the run, so the initial
        # taint set is exactly the initial external set (ADR 0030).
        self.external = set(self.tainted)
        if resume:
            self._from_resume(resume, context)

    def _from_resume(self, resume: list[dict], context: dict) -> None:
        frame = resume[0]
        if (
            frame.get("machine") != self.machine.name
            or frame.get("state") not in self.machine.states
        ):
            self._init_error = RunResult(
                "halt",
                [],
                dict(context),
                error=f"resume-mismatch: frame for {frame.get('machine')!r}"
                f"/{frame.get('state')!r} does not fit machine {self.machine.name!r}",
            )
            return
        self.ctx = dict(frame["ctx"])
        self.state_id = frame["state"]
        self.trace = list(frame["trace"])
        self.steps = frame["steps"]
        self.total_in = frame["total_in"]
        self.total_out = frame["total_out"]
        self.feedback = frame["feedback"]
        self.repair_left = decode_repair(frame["repair_left"])
        # Frames without a taint record (pre-ADR 0025 checkpoints, or values
        # injected by `resume --set`) default to all-tainted — fail-safe.
        self.tainted = set(frame.get("tainted", frame["ctx"].keys()))
        # Same fail-safe for control-flow taint (ADR 0030): a frame that predates
        # the field resumes as externally tainted with a tainted decision, so an
        # old checkpoint cannot launder a decision it never recorded. A human
        # reply injected at THIS resume (`--set human.reply=…`, ADR 0008) is the
        # confirmation the rule asks for, and clears the flag.
        self.external = set(frame.get("external", self.tainted))
        self.flow_tainted = bool(frame.get("flow_tainted", True)) and not _human_confirmed(
            frame, self.ctx
        )
        self.deeper = list(resume[1:]) or None

    def _usage(self) -> dict:
        return {"input_tokens": self.total_in, "output_tokens": self.total_out}

    def _spent(self) -> int:
        return self.total_in + self.total_out

    def _remaining_budget(self) -> int | None:
        if self.cost_budget is None:
            return None
        return max(0, self.cost_budget - self._spent())

    def _snapshot(self, at_steps: int | None = None) -> dict:
        return make_frame(
            self.machine.name,
            self.state_id,
            self.ctx,
            self.steps if at_steps is None else at_steps,
            self.total_in,
            self.total_out,
            self.feedback,
            self.repair_left,
            self.trace,
            self.tainted,
            self.external,
            self.flow_tainted,
        )

    def _suspended(self, reason: str) -> RunResult:
        """Checkpoint this level; nested levels unwind via _Suspend, depth 0 returns."""
        if self.depth:
            raise _Suspend(reason, [self._snapshot()])
        return RunResult(
            "suspended",
            self.trace,
            self.ctx,
            error=reason,
            at=self.state_id,
            usage=self._usage(),
            frames=[self._snapshot()],
        )

    def _suspend_or_halt(self, reason: str) -> RunResult:
        """Loop-top budget exhaustion: checkpoint frames when suspendable, else halt."""
        if self.deps.suspendable:
            return self._suspended(reason)
        return RunResult("halt", self.trace, self.ctx, error=reason, usage=self._usage())

    def _record(self, step: dict) -> None:
        """Append to the trace and mirror it as a live event (ADR 0015)."""
        self.trace.append(step)
        fields: dict = {
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
        _emit(self.deps, "state-done", self.machine.name, self.depth, **fields)

    def _halt(self, error: str, *, at: str | None = None) -> RunResult:
        return RunResult(
            "halt",
            self.trace,
            self.ctx,
            error=error,
            at=at if at is not None else self.state_id,
            usage=self._usage(),
        )

    def go(self) -> RunResult:
        if self._init_error is not None:
            return self._init_error
        _emit(
            self.deps,
            "run-start",
            self.machine.name,
            self.depth,
            entry=self.state_id,
            resumed=bool(self._resume_arg),
        )
        while True:
            early = self._loop_guards()
            if early is not None:
                return early
            # Sub-runs inherit the *remaining* budget so parent+children share one pool.
            self.deps.cost_budget = self._remaining_budget()
            outcome = self._step_once()
            if outcome is not None:
                return outcome

    def _loop_guards(self) -> RunResult | None:
        if self.cancel_requested is not None:
            try:
                cancelled = bool(self.cancel_requested())
            except Exception:
                cancelled = False
            if cancelled:
                return self._halt("cancelled")
        if self.steps >= self.machine.budget:
            return self._suspend_or_halt("budget-exhausted")
        if self.cost_budget is not None and self._spent() >= self.cost_budget:
            return self._suspend_or_halt("cost-exhausted")
        return None

    def _step_once(self) -> RunResult | None:
        """Execute → deposit → judge → transition. None means continue the loop."""
        S = self.machine.states[self.state_id]
        sub_resume, self.deeper = self.deeper, None  # descend into suspended call once
        if sub_resume is not None and S.kind != "call":
            return self._halt(f"resume-mismatch: state {self.state_id!r} is not a call")
        step: dict = {"state": self.state_id, "tier": S.tier or self.machine.default_tier}
        _emit(
            self.deps,
            "state-start",
            self.machine.name,
            self.depth,
            state=self.state_id,
            step=self.steps + 1,
            kind=S.kind,
            tier=step["tier"],
        )

        blocked = self._flow_guard(S, step)
        if blocked is not None:
            return blocked

        exec_out = self._execute_state(S, step, sub_resume)
        if isinstance(exec_out, RunResult):
            return exec_out
        result, judge_reasoning = exec_out

        # DEPOSIT — every deposit is tainted: tool observations and call
        # results are external data, and produce output is derived from
        # untrusted input by an untrusted oracle (SPEC §11).
        _deposit(self.ctx, self.tainted, S, result)
        if _is_external_deposit(S, self.external, self.deps):
            self.external.add(S.output)

        judged = self._judge(S, result, judge_reasoning, step)
        if isinstance(judged, RunResult):
            return judged
        gate, gate_index = judged
        return self._transition(gate, gate_index, result)

    def _flow_guard(self, S: State, step: dict) -> RunResult | None:
        """Refuse (or record) an effect chosen by a judge reading external data.

        SPEC §6 _Control-flow taint_: fencing untrusted values keeps them from
        being read as instructions, but says nothing about the transition a gate
        picks after reading them. This is the missing half — the taint follows the
        **choice**, not just the text, and stops at the effect surface. A `hook:`
        gate or a human reply clears it, which is what makes the rule actionable
        rather than merely alarming: the author's fix is a confirmation gate."""
        if S.kind != "tool" or not self.flow_tainted:
            return None
        if not is_effectful(S.tool, self.deps.tool_effects):
            return None
        step["untrusted_control_flow"] = True
        _emit(
            self.deps,
            "untrusted-control-flow",
            self.machine.name,
            self.depth,
            state=self.state_id,
            tool=S.tool,
            policy=self.deps.on_untrusted_flow,
        )
        if self.deps.on_untrusted_flow != "halt":
            return None
        step.update(step=self.steps, gate=None, policy="untrusted-control-flow", to=None)
        self._record(step)
        return self._halt("untrusted-control-flow")

    def _execute_state(
        self,
        S: State,
        step: dict,
        sub_resume: list[dict] | None,
    ) -> tuple[object, str | None] | RunResult:
        """Run fan-out or single state; update step/tokens/steps. Returns result+reasoning."""
        if S.is_fanout:
            return self._execute_fanout_state(S, step)
        return self._execute_single(S, step, sub_resume)

    def _execute_fanout_state(self, S: State, step: dict) -> tuple[object, str | None] | RunResult:
        fan = _execute_fanout(
            S,
            self.state_id,
            self.ctx,
            self.deps,
            self.machine,
            self.depth,
            self.tainted,
            self.steps,
            self.trace,
            (self.total_in, self.total_out),
            self.flow_tainted,
        )
        if isinstance(fan, RunResult):
            return fan
        result, judge_reasoning, step_in, step_out, self.steps, fan_fields = fan
        step.update(fan_fields)
        self._charge_step(step, step_in, step_out)
        return result, judge_reasoning

    def _handle_suspend(self, s: _Suspend) -> RunResult:
        # A sub-call suspended: prepend this level's loop-top frame and keep unwinding.
        s.frames.insert(0, self._snapshot(at_steps=self.steps - 1))
        if self.depth:
            raise s
        return RunResult(
            "suspended",
            self.trace,
            self.ctx,
            error=s.reason,
            at=s.frames[-1]["state"],
            usage=self._usage(),
            frames=s.frames,
        )

    def _annotate_single_step(
        self,
        step: dict,
        out: object,
        sub: list[dict] | None,
        reasoning: str | None,
        meta: dict,
    ) -> None:
        step["output"] = out if isinstance(out, str) else fmt(out)
        if reasoning:
            step["reasoning"] = reasoning
        if sub is not None:
            step["sub_trace"] = sub
        if meta.get("truncated"):
            step["truncated"] = True
            if meta.get("finish_reason"):
                step["finish_reason"] = meta["finish_reason"]

    def _execute_single(
        self,
        S: State,
        step: dict,
        sub_resume: list[dict] | None,
    ) -> tuple[object, str | None] | RunResult:
        self.steps += 1
        try:
            out, sub, reasoning, (step_in, step_out), meta = _exec_one(
                S,
                self.ctx,
                self.feedback,
                self.deps,
                self.machine,
                self.depth,
                resume=sub_resume,
                tainted=self.tainted,
                flow_tainted=self.flow_tainted,
            )
        except _Suspend as s:
            return self._handle_suspend(s)
        except CallFailed as e:
            return self._halt_call_failed(step, e)
        except RefusalError:
            return self._halt("refusal")
        except ProviderError as e:
            return self._halt(f"provider-error: {e}")
        except Exception as e:  # surface as a clean halt, not a traceback
            return self._halt(f"state-error: {e}")
        self._annotate_single_step(step, out, sub, reasoning, meta)
        self._charge_step(step, step_in, step_out)
        return out, reasoning

    def _halt_call_failed(self, step: dict, e: CallFailed) -> RunResult:
        self.total_in += e.input_tokens
        self.total_out += e.output_tokens
        step["sub_trace"] = e.sub_trace
        if e.input_tokens or e.output_tokens:
            step["cost"] = {
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
            }
        step.update(step=self.steps, gate=None, policy="call-failed", to=None)
        self._record(step)
        return self._halt(f"call-failed: {e.error}")

    def _charge_step(self, step: dict, step_in: int, step_out: int) -> None:
        self.feedback = ""
        self.total_in += step_in
        self.total_out += step_out
        if step_in or step_out:
            previous = step.get("cost", {})
            step["cost"] = {
                "input_tokens": int(previous.get("input_tokens", 0)) + step_in,
                "output_tokens": int(previous.get("output_tokens", 0)) + step_out,
            }

    def _judge(
        self,
        S: State,
        result: object,
        judge_reasoning: str | None,
        step: dict,
    ) -> tuple[Gate, int] | RunResult:
        """Hooks then otherwise then fused LLM prose (SPEC §5). Records the step."""
        eligible = [
            (i, g)
            for i, g in enumerate(S.gates)
            if not (g.kind == "repair" and self.repair_left.get((self.state_id, i), g.repair) == 0)
        ]
        if not eligible:  # every gate was a repair with an exhausted budget
            step.update(step=self.steps, gate=None, policy="no-gate-matched", to=None)
            self._record(step)
            return self._halt("no-gate-matched")
        try:
            judge_model = _judge_model_for(S, self.machine, self.deps)
            i, gate, gann, judge_usage = _select_gate(
                eligible, result, self.ctx, self.deps, judge_reasoning, judge_model
            )
            step.update(gann)
            self._charge_step(step, *judge_usage)
        except JudgeUnparseable:
            step.update(step=self.steps, gate=None, policy="judge-unparseable", to=None)
            if "judge_fallback" not in step:
                step["judge_fallback"] = True
            self._record(step)
            return self._halt("judge-unparseable")
        except RuntimeError as e:
            if str(e) == "no-gate-matched":
                step.update(step=self.steps, gate=None, policy="no-gate-matched", to=None)
                self._record(step)
                return self._halt("no-gate-matched")
            return self._halt(f"state-error: {e}")
        except Exception as e:  # missing hook / host error
            return self._halt(f"state-error: {e}")
        self._update_flow_taint(gann, step)
        step.update(step=self.steps, gate=gate.when, policy=gate.kind, to=gate.to)
        self._record(step)
        return gate, i

    def _update_flow_taint(self, ann: dict, step: dict) -> None:
        """Propagate taint onto the CHOICE, not only the text (SPEC §6 / ADR 0030).

        A gate decided by the host predicate clears the flag — that transition was
        computed by trusted code. A gate decided by the judge sets it whenever any
        external key is in scope: the judge is shown OUTPUT plus the context blob,
        so one poisoned value anywhere in the blackboard is evidence it read.
        `otherwise` reached without consulting a judge neither sets nor clears —
        a default is not a confirmation, and it does not add a new decision."""
        if ann.get("gate_via") == "hook":
            self.flow_tainted = False
            return
        judged = "judge_model" in ann or bool(ann.get("judge_fallback"))
        if judged and self.external:
            self.flow_tainted = True
            step["decision_tainted"] = True

    def _transition(self, gate: Gate, gate_index: int, result: object) -> RunResult | None:
        to, feedback, halt_err = _apply_gate_transition(
            gate,
            gate_index,
            self.state_id,
            repair_left=self.repair_left,
        )
        if halt_err is not None:
            return self._halt(halt_err)
        assert to is not None
        self.feedback = feedback
        if gate.kind == "escalate" and self.deps.escalate_suspend and to != "END":
            # HITL: pause before the handler runs; a resume can drop the human
            # reply into ctx so the handler state sees it (ADR 0008).
            self.state_id = to
            return self._suspended("escalated")
        if to == "END":
            rv = self.ctx.get(self.machine.result) if self.machine.result else result
            return RunResult("done", self.trace, self.ctx, result=rv, usage=self._usage())
        self.state_id = to
        return None


def run(
    machine: Machine,
    context: dict,
    registry: dict,
    llm: LLM,
    tiers: dict[str, str],
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
    on_event: Callable[[dict], None] | None = None,
    on_truncate: str = "report",
    prompt_value_chars: int | None = None,
    cancel_requested: Callable[[], object] | None = None,
    delimit: bool = True,
    trusted_keys: set[str] | None = None,
    on_untrusted_flow: str = "report",
    tool_effects: dict[str, str] | None = None,
    flow_tainted: bool = False,
) -> RunResult:
    """Run a machine and emit one additive terminal event for every outcome.

    ``cancel_requested`` is cooperative and observed between states. Existing
    callers that omit it retain identical semantics.

    ``on_untrusted_flow`` is the control-flow-taint policy (SPEC §6 / ADR 0030):
    ``"report"`` annotates the trace when a judge-made decision over external data
    reaches an effectful tool state; ``"halt"`` refuses the effect.
    ``tool_effects`` lets a host classify its own tools (``"read"`` / ``"effect"``);
    unclassified tools are treated as effectful. ``flow_tainted`` seeds the run's
    control-flow taint — the engine sets it on a sub-run whose `call:` was reached
    by a tainted decision; an embedder that has already made an untrusted routing
    decision of its own can set it too.
    """
    # Keyword, not positional: this list is long and grows with every host policy,
    # and a misordering between two same-typed neighbours (e.g. on_truncate /
    # on_untrusted_flow) would be a silent behaviour swap no type checker catches.
    result = _Runner(
        machine,
        context,
        registry,
        llm,
        tiers,
        judge=judge,
        depth=depth,
        max_workers=max_workers,
        tier_params=tier_params,
        cost_budget=cost_budget,
        tools=tools,
        hooks=hooks,
        suspendable=suspendable,
        escalate_suspend=escalate_suspend,
        resume=resume,
        on_event=on_event,
        on_truncate=on_truncate,
        prompt_value_chars=prompt_value_chars,
        cancel_requested=cancel_requested,
        delimit=delimit,
        trusted_keys=trusted_keys,
        on_untrusted_flow=on_untrusted_flow,
        tool_effects=tool_effects,
        flow_tainted=flow_tainted,
    ).go()
    if on_event is not None:
        with contextlib.suppress(Exception):
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
    return result
