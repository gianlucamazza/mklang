"""Cost accounting, cost budget, error taxonomy, and structured-judge parsing."""

from mklang import engine
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


def test_judge_usage_is_included_in_cost_accounting():
    class JudgeUsageLLM(MockLLM):
        def judge(self, *args, **kwargs):
            self.last_judge_usage = (7, 3)
            return 0

    machine = M(
        {
            "machine": "x",
            "entry": "a",
            "budget": 5,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [{"when": "accepted", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    r = _run(
        machine,
        JudgeUsageLLM(produce_fn=lambda *a: Produced("x", input_tokens=10, output_tokens=5)),
    )
    assert r.usage == {"input_tokens": 17, "output_tokens": 8}
    assert r.trace[0]["cost"] == {"input_tokens": 17, "output_tokens": 8}


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


def test_parse_choice_json_bare_last_number():
    """Fallback order: strict JSON, then whole-reply bare number, then last number."""
    assert parse_choice('{"choice": 2}', 3) == (1, "json")  # JSON, 1-based -> 0-based
    assert parse_choice("2", 3) == (1, "bare")  # entire reply is one integer
    # A verbose/reasoning judge concludes with the answer: take the LAST number, not
    # the first (an earlier "Condition 1 fails" must not be misread as choice 1).
    assert parse_choice("Condition 1 fails. Condition 2 holds. 2", 3) == (1, "last-number")
    assert parse_choice("none apply", 3) == (None, None)  # no digits at all
    # Truncated JSON with no trailing digits is unparseable, not a stray-digit misread.
    assert parse_choice('{"choi', 3) == (None, None)


def test_parse_choice_out_of_range_is_none_not_clamped():
    """0-based model replies and oversized indices must not silently pick gate 0/last."""
    assert parse_choice('{"choice": 0}', 3) == (None, None)  # 0-based misread → -1
    assert parse_choice('{"choice": 4}', 3) == (None, None)  # 1-based past end
    assert parse_choice('{"choice": 1}', 3) == (0, "json")
    assert parse_choice("99", 2) == (None, None)


def test_judge_out_of_range_soft_falls_to_otherwise():
    """Engine must not clamp OOR judge indices; use the traced otherwise path."""
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
    r = _run(m, MockLLM(judge_fn=lambda *a: -1))
    assert r.status == "done"
    assert r.trace[0]["judge_fallback"] is True
    assert r.trace[0]["gate"] == "otherwise"
    assert r.trace[0]["gate_via"] == "otherwise"
    assert "out-of-range" in r.trace[0].get("judge_raw", "")


def test_judge_out_of_range_hard_halts_without_otherwise():
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
    r = _run(m, MockLLM(judge_fn=lambda *a: 99))
    assert r.status == "halt" and r.error == "judge-unparseable"
    assert r.trace[0]["judge_fallback"] is True


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


def test_judge_support_probe_survives_an_adapter_without_judge():
    """An adapter with no `judge` answers False instead of raising.

    `_judge_supports_none` takes `object` — an adapter is whatever a host supplies —
    and used to reach `llm.judge` directly under a `type: ignore[attr-defined]`. The
    checker was right: `AttributeError` is not in the caught set, so an adapter without
    the attribute escaped the probe rather than being answered by it.
    """

    class NoJudge:
        pass

    assert engine._judge_supports_none(NoJudge()) is False


def test_judge_support_probe_reads_the_signature_it_finds():
    class Legacy:
        def judge(self, prompt, options):  # no allow_none
            raise NotImplementedError

    class Modern:
        def judge(self, prompt, options, allow_none=False):
            raise NotImplementedError

    class Kwargs:
        def judge(self, prompt, **kwargs):
            raise NotImplementedError

    assert engine._judge_supports_none(Legacy()) is False
    assert engine._judge_supports_none(Modern()) is True
    assert engine._judge_supports_none(Kwargs()) is True
