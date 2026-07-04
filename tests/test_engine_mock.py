"""Engine semantics against a deterministic MockLLM — no network."""

from mklang.engine import run
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def M(d):
    return parse_machine(d)


def run1(machine, llm, ctx=None, registry=None):
    reg = registry or {machine.name: machine}
    return run(machine, ctx if ctx is not None else dict(machine.context), reg, llm, TIERS, "m")


def gate(when, **kw):
    return {"when": when, **kw}


def test_linear_path():
    m = M(
        {
            "machine": "lin",
            "entry": "a",
            "budget": 5,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="b")],
                },
                "b": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o2",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run1(m, MockLLM(judge_fn=lambda *a: 0))
    assert r.status == "done"
    assert [s["state"] for s in r.trace] == ["a", "b"]


def test_repair_then_ok():
    n = {"c": 0}

    def judge(model, conds, out, ctx):
        n["c"] += 1
        return 1 if n["c"] <= 2 else 0  # repair twice, then the "done" gate

    m = M(
        {
            "machine": "r",
            "entry": "a",
            "budget": 10,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        gate("done", then="ok", to="END"),
                        gate("fix", repair=2, to="a"),
                    ],
                },
            },
        }
    )
    r = run1(m, MockLLM(judge_fn=judge))
    assert r.status == "done"
    assert [s["policy"] for s in r.trace] == ["repair", "repair", "ok"]


def test_escalate_to_handler():
    def judge(model, conds, out, ctx):
        return 0  # always first gate

    m = M(
        {
            "machine": "e",
            "entry": "a",
            "budget": 5,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [gate("needs human", escalate=True, to="h")],
                },
                "h": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o2",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run1(m, MockLLM(judge_fn=judge))
    assert r.status == "done"
    assert r.trace[0]["policy"] == "escalate" and r.trace[1]["state"] == "h"


def test_fail_halts():
    m = M(
        {
            "machine": "f",
            "entry": "a",
            "budget": 5,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        gate("bad", fail=True),
                        gate("otherwise", then="ok", to="END"),
                    ],
                },
            },
        }
    )
    r = run1(m, MockLLM(judge_fn=lambda *a: 0))
    assert r.status == "halt" and r.error == "gate-fail" and r.at == "a"


def test_budget_exhausted():
    m = M(
        {
            "machine": "loop",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="a")],
                },
            },
        }
    )
    r = run1(m, MockLLM(judge_fn=lambda *a: 0))
    assert r.status == "halt" and r.error == "budget-exhausted"
    assert len(r.trace) == 3


def test_fanout_sample_then_reduce():
    llm = MockLLM(produce_fn=lambda *a: Produced("cand"), judge_fn=lambda *a: 0)
    m = M(
        {
            "machine": "sc",
            "entry": "s",
            "budget": 8,
            "result": "answer",
            "states": {
                "s": {
                    "structure": "x",
                    "prompt": "p",
                    "sample": 3,
                    "output": "cands",
                    "gates": [gate("otherwise", then="ok", to="v")],
                },
                "v": {
                    "structure": "x",
                    "prompt": "vote {{cands}}",
                    "output": "answer",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run1(m, llm)
    assert r.status == "done"
    assert r.trace[0]["branches"] == ["cand", "cand", "cand"]
    assert r.result == "cand"


def test_fanout_over_list():
    def produce(model, system, user, reason):
        return Produced(f"seen:{user.split('ITEM:')[-1].strip()}")

    m = M(
        {
            "machine": "mr",
            "entry": "m",
            "budget": 10,
            "result": "summ",
            "states": {
                "m": {
                    "over": "{{items}}",
                    "structure": "x",
                    "prompt": "ITEM:{{item}}",
                    "output": "outs",
                    "gates": [gate("otherwise", then="ok", to="c")],
                },
                "c": {
                    "structure": "x",
                    "prompt": "combine {{outs}}",
                    "output": "summ",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run1(m, MockLLM(produce_fn=produce, judge_fn=lambda *a: 0), ctx={"items": ["a", "b"]})
    assert r.trace[0]["branches"] == ["seen:a", "seen:b"]


def test_call_submachine_nests_trace():
    sub = M(
        {
            "machine": "sub",
            "entry": "s",
            "budget": 3,
            "result": "r",
            "states": {
                "s": {
                    "structure": "x",
                    "prompt": "{{text}}",
                    "output": "r",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    parent = M(
        {
            "machine": "par",
            "entry": "c",
            "budget": 5,
            "result": "out",
            "states": {
                "c": {
                    "call": "sub",
                    "input": {"text": "{{msg}}"},
                    "output": "out",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    llm = MockLLM(
        produce_fn=lambda model, system, user, reason: Produced(f"got:{user}"),
        judge_fn=lambda *a: 0,
    )
    r = run(parent, {"msg": "hi"}, {"sub": sub, "par": parent}, llm, TIERS, "m")
    assert r.status == "done"
    assert r.result == "got:hi"
    assert "sub_trace" in r.trace[0]


def test_over_plus_call_map_reduce():
    worker = M(
        {
            "machine": "w",
            "entry": "s",
            "budget": 3,
            "result": "r",
            "states": {
                "s": {
                    "structure": "x",
                    "prompt": "sum:{{text}}",
                    "output": "r",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    parent = M(
        {
            "machine": "mr",
            "entry": "map",
            "budget": 12,
            "result": "summ",
            "states": {
                "map": {
                    "over": "{{chunks}}",
                    "call": "w",
                    "input": {"text": "{{item}}"},
                    "output": "outs",
                    "gates": [gate("otherwise", then="ok", to="c")],
                },
                "c": {
                    "structure": "x",
                    "prompt": "combine {{outs}}",
                    "output": "summ",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    llm = MockLLM(
        produce_fn=lambda model, system, user, reason: Produced(user), judge_fn=lambda *a: 0
    )
    r = run(parent, {"chunks": ["a", "b"]}, {"w": worker, "mr": parent}, llm, TIERS, "m")
    assert r.status == "done"
    # each branch ran the worker sub-machine on its item
    assert r.trace[0]["branches"] == ["sum:a", "sum:b"]
    assert "sub_trace" in r.trace[0] and len(r.trace[0]["sub_trace"]) == 2


def test_no_gate_matched_when_all_repair_exhausted():
    def judge(model, conds, out, ctx):
        return 0  # always the (only) repair gate while it is eligible

    m = M(
        {
            "machine": "x",
            "entry": "a",
            "budget": 10,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [gate("fix", repair=1, to="a")],
                },
            },
        }
    )
    r = run1(m, MockLLM(judge_fn=judge))
    assert r.status == "halt" and r.error == "no-gate-matched"


def test_accumulate_grows_a_list():
    n = {"c": 0}

    def judge(model, conds, out, ctx):
        n["c"] += 1
        return 0 if n["c"] >= 3 else 1  # loop twice, then done

    m = M(
        {
            "machine": "acc",
            "entry": "a",
            "budget": 10,
            "result": "log",
            "states": {
                "a": {
                    "structure": "x",
                    "prompt": "p",
                    "accumulate": True,
                    "output": "log",
                    "gates": [
                        gate("done", then="ok", to="END"),
                        gate("more", then="ok", to="a"),
                    ],
                },
            },
        }
    )
    r = run1(m, MockLLM(produce_fn=lambda *a: Produced("x"), judge_fn=judge), ctx={})
    assert r.status == "done"
    assert r.context["log"] == ["x", "x", "x"]


def test_tier_params_reach_produce():
    llm = MockLLM()  # default produce records each call incl. params
    m = M(
        {
            "machine": "p",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "x",
                    "prompt": "p",
                    "tier": "reasoning",
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    run(m, {}, {"p": m}, llm, TIERS, "m", tier_params={"reasoning": {"effort": "high"}})
    assert any(c["params"] == {"effort": "high"} for c in llm.calls)


def test_fanout_reason_captures_reasonings():
    llm = MockLLM(produce_fn=lambda *a: Produced("c", reasoning="r"))
    m = M(
        {
            "machine": "f",
            "entry": "s",
            "budget": 6,
            "result": "o",
            "states": {
                "s": {
                    "structure": "x",
                    "prompt": "p",
                    "sample": 2,
                    "reason": True,
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run1(m, llm)
    assert r.trace[0]["reasonings"] == ["r", "r"]


def test_state_error_halts_cleanly():
    def boom(*a):
        raise RuntimeError("kaboom")

    m = M(
        {
            "machine": "e",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "x",
                    "prompt": "p",
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run1(m, MockLLM(produce_fn=boom))
    assert r.status == "halt" and r.error.startswith("state-error")


def test_reason_recorded_in_trace():
    llm = MockLLM(produce_fn=lambda *a: Produced("ans", reasoning="because"))
    m = M(
        {
            "machine": "cot",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "x",
                    "prompt": "p",
                    "reason": True,
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run1(m, llm)
    assert r.trace[0]["reasoning"] == "because"
