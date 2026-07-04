"""`tool` states: host-callable dispatch, unknown-tool safety, fan-out, and calc."""

from mklang.engine import run
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine
from mklang.tools import calc

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def M(d):
    return parse_machine(d)


def test_calc_builtin_safe():
    assert calc({"expr": "(17+4)*3"}) == "63"
    assert calc({"expr": "2**10"}) == "1024"
    assert "error" in calc({"expr": "__import__('os').system('x')"})  # not arithmetic


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
