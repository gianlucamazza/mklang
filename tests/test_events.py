"""The on_event observability seam (ADR 0015): events mirror the trace, never affect the run."""

from mklang.engine import run
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def M(d):
    return parse_machine(d)


def echo():
    return MockLLM(
        produce_fn=lambda model, system, user, reason: Produced(text=user),
        judge_fn=lambda *a: 0,
    )


def linear():
    return M(
        {
            "machine": "lin",
            "entry": "a",
            "budget": 5,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "one",
                    "output": "o1",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "b"}],
                },
                "b": {
                    "structure": "s",
                    "prompt": "two",
                    "output": "o2",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )


def collect(machine, llm=None, registry=None, **kw):
    events = []
    res = run(
        machine,
        dict(machine.context),
        registry or {machine.name: machine},
        llm or echo(),
        TIERS,
        "m",
        on_event=events.append,
        **kw,
    )
    return res, events


def test_events_mirror_the_trace():
    res, events = collect(linear())
    assert res.status == "done"
    kinds = [e["type"] for e in events]
    assert kinds == [
        "run-start",
        "state-start",
        "state-done",
        "state-start",
        "state-done",
        "run-finished",
    ]
    done = [e for e in events if e["type"] == "state-done"]
    for ev, step in zip(done, res.trace):
        assert ev["state"] == step["state"]
        assert ev["gate"] == step["gate"]
        assert ev["policy"] == step["policy"]
        assert ev["to"] == step["to"]
        assert ev["step"] == step["step"]
        assert ev["depth"] == 0 and ev["machine"] == "lin"


def test_nested_call_events_carry_depth():
    child = M(
        {
            "machine": "child",
            "entry": "w",
            "budget": 3,
            "result": "o",
            "states": {
                "w": {
                    "structure": "s",
                    "prompt": "inner",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    parent = M(
        {
            "machine": "parent",
            "entry": "c",
            "budget": 3,
            "states": {
                "c": {
                    "call": "child",
                    "output": "sub",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    res, events = collect(parent, registry={"parent": parent, "child": child})
    assert res.status == "done"
    child_events = [e for e in events if e["machine"] == "child"]
    assert {e["depth"] for e in child_events} == {1}
    assert [e["type"] for e in child_events] == [
        "run-start",
        "state-start",
        "state-done",
        "run-finished",
    ]
    # the child completes before the parent's call state is recorded
    parent_done = events.index(
        next(e for e in events if e["type"] == "state-done" and e["machine"] == "parent")
    )
    assert events.index(child_events[-1]) < parent_done


def test_fanout_emits_branch_done_with_index():
    m = M(
        {
            "machine": "fan",
            "entry": "s",
            "budget": 8,
            "states": {
                "s": {
                    "structure": "s",
                    "prompt": "branch {{index}}",
                    "sample": 3,
                    "output": "outs",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    res, events = collect(m)
    assert res.status == "done"
    branches = [e for e in events if e["type"] == "branch-done"]
    assert sorted(e["index"] for e in branches) == [0, 1, 2]
    done = next(e for e in events if e["type"] == "state-done")
    assert done["branches"] == 3


def test_hitl_suspension_records_the_escalating_state():
    m = M(
        {
            "machine": "h",
            "entry": "draft",
            "budget": 5,
            "states": {
                "draft": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "d",
                    "gates": [
                        {"when": "risky", "escalate": True, "to": "review"},
                        {"when": "otherwise", "then": "ok", "to": "END"},
                    ],
                },
                "review": {
                    "structure": "s",
                    "prompt": "{{human.reply}}",
                    "output": "f",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    res, events = collect(m, suspendable=True, escalate_suspend=True)
    assert res.status == "suspended"
    assert events[-2]["type"] == "state-done" and events[-2]["policy"] == "escalate"
    assert events[-1]["type"] == "run-finished" and events[-1]["status"] == "suspended"


def test_cooperative_cancellation_and_terminal_event():
    m = linear()
    checks = iter([False, True])
    res, events = collect(m, cancel_requested=lambda: next(checks, True))
    assert res.status == "halt" and res.error == "cancelled"
    assert [step["state"] for step in res.trace] == ["a"]
    assert events[-1]["type"] == "run-finished"
    assert events[-1]["error"] == "cancelled"


def test_state_done_event_carries_truncated_flag():
    m = M(
        {
            "machine": "t",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "long",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    llm = MockLLM(
        produce_fn=lambda *a: Produced(text="partial", truncated=True, finish_reason="length")
    )
    res, events = collect(m, llm=llm)
    assert res.status == "done"
    assert res.trace[0].get("truncated") is True
    done = [e for e in events if e["type"] == "state-done"][0]
    assert done.get("truncated") is True
    assert done.get("finish_reason") == "length"


def test_output_preview_is_truncated():
    llm = MockLLM(produce_fn=lambda *a: Produced(text="x" * 500), judge_fn=lambda *a: 0)
    _, events = collect(linear(), llm=llm)
    done = next(e for e in events if e["type"] == "state-done")
    assert len(done["output"]) == 200 and done["output"].endswith("…")


def test_raising_observer_never_affects_the_run():
    def bomb(event):
        raise RuntimeError("observer exploded")

    m = linear()
    res = run(m, {}, {m.name: m}, echo(), TIERS, "m", on_event=bomb)
    assert res.status == "done"
    assert len(res.trace) == 2
