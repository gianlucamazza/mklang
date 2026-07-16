"""Cost accounting, cost budget, error taxonomy, and structured-judge parsing."""

from mklang.engine import run
from mklang.errors import ProviderError, RefusalError
from mklang.llm.base import Produced, parse_choice
from mklang.llm.mock import MockLLM, UnparseableJudgeLLM
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def M(d):
    return parse_machine(d)


def _one_state(gates_to="END", budget=5):
    return M(
        {
            "machine": "x",
            "entry": "a",
            "budget": budget,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": gates_to}],
                },
            },
        }
    )


def _run(m, llm, **kw):
    return run(m, {}, {m.name: m}, llm, TIERS, "m", **kw)


def test_usage_recorded_in_trace_and_result():
    llm = MockLLM(produce_fn=lambda *a: Produced("x", input_tokens=10, output_tokens=5))
    r = _run(_one_state(), llm)
    assert r.usage == {"input_tokens": 10, "output_tokens": 5}
    assert r.trace[0]["cost"] == {"input_tokens": 10, "output_tokens": 5}


def test_cost_budget_halts():
    llm = MockLLM(produce_fn=lambda *a: Produced("x", input_tokens=100, output_tokens=0))
    r = _run(_one_state(gates_to="a", budget=99), llm, cost_budget=150)
    assert r.status == "halt" and r.error == "cost-exhausted"
    assert r.usage["input_tokens"] == 200  # two steps ran before the budget tripped


def test_cost_budget_shared_with_submachine():
    """Parent cost_budget must cap tokens spent inside call children."""
    child = M(
        {
            "machine": "child",
            "entry": "c",
            "budget": 20,
            "result": "r",
            "states": {
                "c": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "r",
                    # loop so it would keep spending without a shared budget
                    "gates": [{"when": "otherwise", "then": "ok", "to": "c"}],
                },
            },
        }
    )
    parent = M(
        {
            "machine": "parent",
            "entry": "a",
            "budget": 20,
            "states": {
                "a": {
                    "call": "child",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    llm = MockLLM(produce_fn=lambda *a: Produced("x", input_tokens=40, output_tokens=0))
    r = run(
        parent,
        {},
        {"parent": parent, "child": child},
        llm,
        TIERS,
        "m",
        cost_budget=100,
    )
    assert r.status == "halt"
    assert "call-failed: cost-exhausted" in (r.error or "")
    assert r.usage["input_tokens"] <= 120  # a few child steps, not unbounded


def test_refusal_halts_with_reason():
    def boom(*a):
        raise RefusalError("declined")

    r = _run(_one_state(), MockLLM(produce_fn=boom))
    assert r.status == "halt" and r.error == "refusal" and r.at == "a"


def test_provider_error_halts_with_reason():
    def boom(*a):
        raise ProviderError("500 server error")

    r = _run(_one_state(), MockLLM(produce_fn=boom))
    assert r.status == "halt" and r.error.startswith("provider-error")


def test_parse_choice_json_then_regex_then_none():
    assert parse_choice('{"choice": 2}', 3) == 1  # JSON, 1-based -> 0-based
    assert parse_choice("the first condition holds: 3", 3) == 2  # bare number
    assert parse_choice("unparseable", 3) is None  # caller decides fallback/halt


def test_judge_unparseable_soft_falls_to_otherwise():
    # Prose gate first forces LLM judge; otherwise is the soft-fallback sink.
    m = M(
        {
            "machine": "x",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        {"when": "quality is high", "then": "ok", "to": "END"},
                        {"when": "otherwise", "then": "ok", "to": "END"},
                    ],
                },
            },
        }
    )
    r = _run(m, UnparseableJudgeLLM())
    assert r.status == "done"
    assert r.trace[0]["judge_fallback"] is True
    assert r.trace[0]["gate"] == "otherwise"
    assert r.trace[0]["gate_via"] == "otherwise"


def test_judge_unparseable_hard_halts_without_otherwise():
    m = M(
        {
            "machine": "x",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        {"when": "quality is high", "then": "ok", "to": "END"},
                        {"when": "needs work", "repair": 1, "to": "a"},
                    ],
                },
            },
        }
    )
    r = _run(m, UnparseableJudgeLLM())
    assert r.status == "halt" and r.error == "judge-unparseable"
    assert r.trace[0]["judge_fallback"] is True


def test_missing_tier_halts_with_clear_message():
    m = M(
        {
            "machine": "x",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "tier": "reasoning",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    # provider map missing `reasoning`
    r = run(m, {}, {m.name: m}, MockLLM(), {"fast": "m", "balanced": "m"}, "m")
    assert r.status == "halt"
    assert "tier 'reasoning' not configured" in (r.error or "")


def test_over_missing_path_halts():
    m = M(
        {
            "machine": "mr",
            "entry": "m",
            "budget": 5,
            "states": {
                "m": {
                    "over": "{{missing}}",
                    "structure": "x",
                    "prompt": "p",
                    "output": "outs",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    r = _run(m, MockLLM())
    assert r.status == "halt"
    assert "not found in context" in (r.error or "")


def test_over_empty_list_ok():
    m = M(
        {
            "machine": "mr",
            "entry": "m",
            "budget": 5,
            "states": {
                "m": {
                    "over": "{{items}}",
                    "structure": "x",
                    "prompt": "p",
                    "output": "outs",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    r = run(m, {"items": []}, {m.name: m}, MockLLM(), TIERS, "m")
    assert r.status == "done"
    assert r.trace[0]["branches"] == []
