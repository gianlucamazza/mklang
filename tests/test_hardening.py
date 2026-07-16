"""Cost accounting, cost budget, error taxonomy, and structured-judge parsing."""

from mklang.engine import run
from mklang.errors import ProviderError, RefusalError
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.llm.openai_compat import _parse_choice
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


def test_parse_choice_json_then_regex_then_fallback():
    assert _parse_choice('{"choice": 2}', 3) == 1  # JSON, 1-based -> 0-based
    assert _parse_choice("the first condition holds: 3", 3) == 2  # bare number
    assert _parse_choice("unparseable", 3) == 2  # fallback to last (catch-all)


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
