"""A frozen golden trace — regression guard on step numbering, gates, and transitions."""

from mklang.engine import run
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def test_golden_trace_linear_with_one_repair():
    def produce(*a):
        return Produced("out")  # 0 tokens → no `cost` key in the trace

    def judge(model, conds, out, ctx):
        if conds == ["otherwise"]:
            return 0
        if "fix" in conds:
            return conds.index("fix")  # repair while eligible
        return 0  # "done"

    m = parse_machine(
        {
            "machine": "g",
            "entry": "a",
            "budget": 10,
            "states": {
                "a": {
                    "structure": "x",
                    "prompt": "p",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "b"}],
                },
                "b": {
                    "structure": "x",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        {"when": "done", "then": "ok", "to": "END"},
                        {"when": "fix", "repair": 1, "to": "b"},
                    ],
                },
            },
        }
    )
    r = run(m, {}, {"g": m}, MockLLM(produce_fn=produce, judge_fn=judge), TIERS, "m")

    assert r.status == "done"
    assert r.trace == [
        {
            "state": "a",
            "tier": "balanced",
            "output": "out",
            "gate_via": "otherwise",
            "step": 1,
            "gate": "otherwise",
            "policy": "ok",
            "to": "b",
        },
        {
            "state": "b",
            "tier": "balanced",
            "output": "out",
            "gate_via": "llm",
            "judge_model": "m",
            "step": 2,
            "gate": "fix",
            "policy": "repair",
            "to": "b",
        },
        {
            "state": "b",
            "tier": "balanced",
            "output": "out",
            "gate_via": "llm",
            "judge_model": "m",
            "step": 3,
            "gate": "done",
            "policy": "ok",
            "to": "END",
        },
    ]
