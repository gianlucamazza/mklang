"""`tool` states: host-callable dispatch, unknown-tool safety, fan-out, and calc."""

from mklang.engine import run
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine
from mklang.tools import BUILTINS, calc, load_tool_registry, search_kb, send_reply

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def M(d):
    return parse_machine(d)


def test_calc_builtin_safe():
    assert calc({"expr": "(17+4)*3"}) == "63"
    assert calc({"expr": "2**10"}) == "1024"
    assert "error" in calc({"expr": "__import__('os').system('x')"})  # not arithmetic


def test_search_kb_and_send_reply_stubs():
    kb = search_kb({"query": "billing refund"})
    assert "[kb stub]" in kb and "billing refund" in kb
    assert search_kb({}) == "[kb] empty query — no facts"
    sent = send_reply({"body": "Hello customer, your refund is approved."})
    assert sent.startswith("[sent]") and "chars=" in sent
    assert "search_kb" in BUILTINS and "send_reply" in BUILTINS


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
    # extra wins over builtin name collision
    reg2 = load_tool_registry(extra={"calc": lambda d: "override"}, include_entry_points=False)
    assert reg2["calc"]({}) == "override"


def test_load_tool_registry_includes_entry_points_when_installed():
    # In editable/install, our own package registers calc/search; still must be present.
    reg = load_tool_registry(include_entry_points=True)
    assert "calc" in reg and "search" in reg
    assert reg["calc"]({"expr": "1+1"}) == "2"
