"""`tool` states: host-callable dispatch, unknown-tool safety, fan-out, and calc."""

import json

from mklang.engine import run
from mklang.kb import FakeKBBackend, configure_kb
from mklang.llm.mock import MockLLM
from mklang.mail import FakeMailBackend, configure_mail
from mklang.model import parse_machine
from mklang.tools import BUILTINS, calc, load_tool_registry, search_kb, send_reply

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def setup_function(_fn):
    configure_kb(None)
    configure_mail(None)


def teardown_function(_fn):
    configure_kb(None)
    configure_mail(None)


def M(d):
    return parse_machine(d)


def test_calc_builtin_safe():
    assert calc({"expr": "(17+4)*3"}) == "63"
    assert calc({"expr": "2**10"}) == "1024"
    assert "error" in calc({"expr": "__import__('os').system('x')"})  # not arithmetic


def test_search_kb_structured_stub():
    kb = json.loads(search_kb({"query": "billing refund"}))
    assert kb["tool"] == "search_kb"
    assert kb["stub"] is True
    assert kb["error"] is None
    assert kb["query"] == "billing refund"
    assert any("Billing" in f or "billing" in f.lower() for f in kb["facts"])
    empty = json.loads(search_kb({}))
    assert empty["error"] == "empty query" and empty["facts"] == []
    assert "search_kb" in BUILTINS


def test_send_reply_stub_does_not_claim_real_send():
    sent = json.loads(send_reply({"body": "Hello customer, your refund is approved."}))
    assert sent["tool"] == "send_reply"
    assert sent["stub"] is True
    assert sent["sent"] is False
    assert sent["recorded"] is True
    assert sent["delivery"] == "stub"
    assert sent["chars"] > 0
    assert "send_reply" in BUILTINS
    empty = json.loads(send_reply({}))
    assert empty["error"] == "empty body" and empty["sent"] is False


def test_fake_kb_and_mail_backends():
    configure_kb(FakeKBBackend(facts=["only-fact"]))
    kb = json.loads(search_kb({"query": "x"}))
    assert kb["facts"] and "only-fact" in kb["facts"][0]
    assert kb["stub"] is True

    box = FakeMailBackend()
    configure_mail(box)
    out = json.loads(send_reply({"body": "hi", "to": "a@b.c"}))
    assert out["sent"] is True
    assert out["delivery"] == "fake"
    assert out["stub"] is True  # fake is not live SMTP
    assert len(box.outbox) == 1 and box.outbox[0].to == "a@b.c"


def test_tool_state_runs_and_deposits_observation():
    m = M(
        {
            "machine": "t",
            "entry": "a",
            "budget": 5,
            "result": "o",
            "states": {
                "a": {
                    "tool": "echo",
                    "input": {"x": "{{v}}"},
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    tools = {"echo": lambda inp: f"echoed:{inp['x']}"}
    r = run(m, {"v": "hi"}, {"t": m}, MockLLM(), TIERS, "m", tools=tools)
    assert r.status == "done" and r.result == "echoed:hi"
    assert r.trace[0]["output"] == "echoed:hi"


def test_unknown_tool_halts_cleanly():
    m = M(
        {
            "machine": "t",
            "entry": "a",
            "budget": 5,
            "states": {
                "a": {
                    "tool": "nope",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    r = run(m, {}, {"t": m}, MockLLM(), TIERS, "m", tools={})
    assert r.status == "halt" and r.error.startswith("state-error")


def test_fanout_over_a_tool():
    m = M(
        {
            "machine": "t",
            "entry": "a",
            "budget": 8,
            "result": "o",
            "states": {
                "a": {
                    "over": "{{items}}",
                    "tool": "dbl",
                    "input": {"n": "{{item}}"},
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    tools = {"dbl": lambda inp: str(int(inp["n"]) * 2)}
    r = run(m, {"items": ["2", "5"]}, {"t": m}, MockLLM(), TIERS, "m", tools=tools)
    assert r.trace[0]["branches"] == ["4", "10"]


def test_load_tool_registry_merges_builtins_and_extra():
    reg = load_tool_registry(extra={"echo": lambda d: d.get("x", "")}, include_entry_points=False)
    assert set(BUILTINS) <= set(reg)
    assert reg["echo"]({"x": "hi"}) == "hi"
    reg2 = load_tool_registry(extra={"calc": lambda d: "override"}, include_entry_points=False)
    assert reg2["calc"]({}) == "override"


def test_load_tool_registry_includes_entry_points_when_installed():
    reg = load_tool_registry(include_entry_points=True)
    assert "calc" in reg and "search" in reg
    assert reg["calc"]({"expr": "1+1"}) == "2"
