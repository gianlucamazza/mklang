"""Code-hook gates: host predicates fire without the LLM (ADR 0006)."""

from mklang.engine import run
from mklang.hooks import BUILTINS, auto_approve_ok, load_hook_registry
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.loader import semantic_check
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def M(d):
    return parse_machine(d)


def test_hook_true_fires_without_llm_judge():
    judged = {"n": 0}

    def judge(*a, **k):
        judged["n"] += 1
        return 0

    m = M(
        {
            "machine": "h",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        {
                            "when": "exact ok",
                            "hook": "always_true",
                            "then": "ok",
                            "to": "END",
                        },
                        {"when": "otherwise", "then": "ok", "to": "END"},
                    ],
                },
            },
        }
    )
    r = run(
        m,
        {},
        {m.name: m},
        MockLLM(produce_fn=lambda *a: Produced("x"), judge_fn=judge),
        TIERS,
        "m",
        hooks=BUILTINS,
    )
    assert r.status == "done"
    assert judged["n"] == 0  # no LLM judge
    assert r.trace[0]["gate_via"] == "hook"
    assert r.trace[0]["hook"] == "always_true"
    assert r.trace[0]["gate"] == "exact ok"


def test_hook_false_falls_through_to_otherwise():
    m = M(
        {
            "machine": "h",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        {
                            "when": "never",
                            "hook": "always_false",
                            "then": "ok",
                            "to": "END",
                        },
                        {"when": "otherwise", "escalate": True, "to": "b"},
                    ],
                },
                "b": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o2",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    r = run(
        m,
        {},
        {m.name: m},
        MockLLM(produce_fn=lambda *a: Produced("x"), judge_fn=lambda *a: 0),
        TIERS,
        "m",
        hooks=BUILTINS,
    )
    assert r.status == "done"
    assert r.trace[0]["policy"] == "escalate" and r.trace[0]["to"] == "b"
    assert r.trace[0]["gate_via"] == "otherwise"


def test_auto_approve_ok_uses_context():
    assert auto_approve_ok({"amount": 45, "has_receipt": True}, None) is True
    assert auto_approve_ok({"amount": 200, "has_receipt": True}, None) is False
    assert auto_approve_ok({"amount": 45, "has_receipt": False}, None) is False


def test_unknown_hook_halts():
    m = M(
        {
            "machine": "h",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        {"when": "x", "hook": "missing", "then": "ok", "to": "END"},
                        {"when": "otherwise", "then": "ok", "to": "END"},
                    ],
                },
            },
        }
    )
    r = run(
        m,
        {},
        {m.name: m},
        MockLLM(produce_fn=lambda *a: Produced("x")),
        TIERS,
        "m",
        hooks={},
    )
    assert r.status == "halt"
    assert "unknown hook" in (r.error or "")


def test_semantic_check_warns_undeclared_hook():
    m = M(
        {
            "machine": "h",
            "entry": "a",
            "budget": 3,
            "hooks": [{"name": "always_true"}],
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        {
                            "when": "x",
                            "hook": "nope",
                            "then": "ok",
                            "to": "END",
                        },
                    ],
                },
            },
        }
    )
    _, warnings = semantic_check(m, {m.name: m})
    assert any("hook 'nope'" in w for w in warnings)


def test_example_hook_gates_machine_validates():
    from mklang.loader import load_dict, load_machine, validate_dict

    d = load_dict("examples/hook_gates.mk")
    validate_dict(d)
    m = load_machine("examples/hook_gates.mk")
    r = run(
        m,
        dict(m.context),
        {m.name: m},
        MockLLM(produce_fn=lambda *a: Produced("note ok")),
        TIERS,
        "m",
        hooks=BUILTINS,
    )
    assert r.status == "done"
    assert r.trace[0]["gate_via"] == "hook"
    assert r.trace[0]["to"] == "END"


def test_load_hook_registry_merges_extra():
    reg = load_hook_registry(
        extra={"always_true": lambda c, o: False},
        include_entry_points=False,
    )
    assert reg["always_true"]({}, None) is False  # extra overrides builtin
    assert reg["auto_approve_ok"]({"amount": 1, "has_receipt": True}, None) is True
