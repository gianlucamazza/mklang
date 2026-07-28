"""Control-flow taint (SPEC §6 / ADR 0030): the taint follows the CHOICE.

ADR 0025 keeps untrusted values from being read as instructions. These tests pin
the other half — an injection that persuades the judge to fire a gate into an
effectful state is a decision made by external data, and the runtime says so.
"""

import pytest

from mklang.controlflow import is_effectful, machine_touches_tools
from mklang.engine import run
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def gate(when, **kw):
    return {"when": when, **kw}


def machine(*, first_gate=None, tool="write_file"):
    """entry `read` → (gate) → `act`, a tool state. Context key `request` is
    host-suppliable, which is what makes the run externally tainted."""
    return parse_machine(
        {
            "machine": "cf",
            "entry": "read",
            "budget": 6,
            "context": {"request": ""},
            "states": {
                "read": {
                    "structure": "s",
                    "prompt": "Handle: {{request}}",
                    "output": "plan",
                    "gates": [
                        first_gate or gate("the plan is to act", then="ok", to="act"),
                        gate("otherwise", then="ok", to="END"),
                    ],
                },
                "act": {
                    "tool": tool,
                    "input": {"path": "out.txt", "content": "{{plan}}"},
                    "output": "done",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )


def go(m, *, ctx=None, policy="report", hooks=None, tool_effects=None):
    return run(
        m,
        ctx if ctx is not None else {"request": "please write it"},
        {m.name: m},
        MockLLM(judge_fn=lambda *a: 0),
        TIERS,
        "m",
        tools={"write_file": lambda i: "written", "search_kb": lambda i: "[kb] fact"},
        hooks=hooks or {},
        on_untrusted_flow=policy,
        tool_effects=tool_effects,
    )


def test_judged_decision_over_external_data_marks_the_effect():
    r = go(machine())
    assert r.status == "done"
    assert r.trace[0]["decision_tainted"] is True
    assert r.trace[1]["untrusted_control_flow"] is True


def test_halt_policy_refuses_the_effect():
    r = go(machine(), policy="halt")
    assert (r.status, r.error, r.at) == ("halt", "untrusted-control-flow", "act")
    # The effect never ran: the tool state has no output in the recorded step.
    assert r.trace[-1]["policy"] == "untrusted-control-flow"
    assert "done" not in r.context


def test_hook_gate_confirms_the_transition():
    """The author's fix is a confirmation gate — not a prompt, a `hook:`."""
    confirmed = machine(first_gate=gate("the host approves", hook="approved", then="ok", to="act"))
    r = go(confirmed, policy="halt", hooks={"approved": lambda ctx, out: True})
    assert r.status == "done"
    assert r.trace[0]["gate_via"] == "hook"
    assert "untrusted_control_flow" not in r.trace[1]


def test_read_only_tool_is_not_an_effect():
    r = go(machine(tool="search_kb"), policy="halt")
    assert r.status == "done"
    assert "untrusted_control_flow" not in r.trace[1]


def test_host_may_classify_its_own_tools():
    r = go(machine(tool="search_kb"), policy="halt", tool_effects={"search_kb": "effect"})
    assert r.error == "untrusted-control-flow"


def test_author_only_context_is_not_externally_tainted():
    """A run with nothing from outside has nothing to steer the decision: the
    machine's own literal is trusted, so the same route is clean."""
    m = machine()
    r = run(
        m,
        dict(m.context),  # untouched author literals
        {m.name: m},
        MockLLM(judge_fn=lambda *a: 0),
        TIERS,
        "m",
        tools={"write_file": lambda i: "written"},
        on_untrusted_flow="halt",
    )
    assert r.status == "done"
    assert "decision_tainted" not in r.trace[0]


def test_tool_observation_taints_later_decisions():
    """Nothing was host-supplied, but a tool observation is external data — and
    the judge sees the whole blackboard, so it taints the next decision."""
    m = parse_machine(
        {
            "machine": "cf2",
            "entry": "lookup",
            "budget": 6,
            "states": {
                "lookup": {
                    "tool": "search_kb",
                    "input": {"query": "refunds"},
                    "output": "facts",
                    "gates": [gate("otherwise", then="ok", to="decide")],
                },
                "decide": {
                    "structure": "s",
                    "prompt": "Given {{facts}}, what next?",
                    "output": "plan",
                    "gates": [
                        gate("the plan is to write it down", then="ok", to="act"),
                        gate("otherwise", then="ok", to="END"),
                    ],
                },
                "act": {
                    "tool": "write_file",
                    "input": {"path": "o.txt", "content": "{{plan}}"},
                    "output": "done",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run(
        m,
        {},
        {m.name: m},
        MockLLM(judge_fn=lambda *a: 0),
        TIERS,
        "m",
        tools={"search_kb": lambda i: "[kb] fact", "write_file": lambda i: "written"},
        on_untrusted_flow="halt",
    )
    assert (r.status, r.error) == ("halt", "untrusted-control-flow")


def test_checkpoint_frames_carry_the_flow_state():
    """A suspended run must not launder its decision through the checkpoint."""
    m = machine()
    m.budget = 1  # suspend at the loop top, right after the judged decision
    r = run(
        m,
        {"request": "please write it"},
        {m.name: m},
        MockLLM(judge_fn=lambda *a: 0),
        TIERS,
        "m",
        tools={"write_file": lambda i: "written"},
        suspendable=True,
    )
    assert r.status == "suspended" and r.frames
    frame = r.frames[0]
    assert "flow_tainted" in frame and "external" in frame
    assert "request" in frame["external"]


def test_resume_without_the_field_fails_safe():
    """A pre-ADR-0030 frame resumes as tainted, not as trusted."""
    m = machine()
    legacy = {
        "machine": "cf",
        "state": "act",
        "ctx": {"request": "x", "plan": "act"},
        "steps": 1,
        "total_in": 0,
        "total_out": 0,
        "feedback": "",
        "repair_left": [],
        "trace": [],
        "tainted": ["request", "plan"],
    }
    r = run(
        m,
        {},
        {m.name: m},
        MockLLM(judge_fn=lambda *a: 0),
        TIERS,
        "m",
        tools={"write_file": lambda i: "written"},
        resume=[legacy],
        on_untrusted_flow="halt",
    )
    assert r.error == "untrusted-control-flow"


def test_human_reply_at_resume_clears_the_flag():
    """HITL is the other confirmation: a human decided, so the effect proceeds."""
    m = machine()
    approved = {
        "machine": "cf",
        "state": "act",
        "ctx": {"request": "x", "plan": "act", "human": {"reply": "approved"}},
        "steps": 1,
        "total_in": 0,
        "total_out": 0,
        "feedback": "",
        "repair_left": [],
        "trace": [],
        "tainted": ["request", "plan", "human"],
    }
    r = run(
        m,
        {},
        {m.name: m},
        MockLLM(judge_fn=lambda *a: 0),
        TIERS,
        "m",
        tools={"write_file": lambda i: "written"},
        resume=[approved],
        on_untrusted_flow="halt",
    )
    assert r.status == "done"


def test_unknown_tools_are_effectful_by_default():
    assert is_effectful("write_file") is True
    assert is_effectful("search_kb") is False
    assert is_effectful("some_third_party_plugin") is True
    assert is_effectful("some_third_party_plugin", {"some_third_party_plugin": "read"}) is False
    assert is_effectful(None) is False


def test_machine_touches_tools_follows_calls_without_looping():
    leaf = parse_machine(
        {
            "machine": "leaf",
            "entry": "t",
            "budget": 3,
            "states": {
                "t": {
                    "tool": "write_file",
                    "input": {},
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="END")],
                }
            },
        }
    )
    parent = parse_machine(
        {
            "machine": "parent",
            "entry": "c",
            "budget": 3,
            "states": {
                "c": {
                    "call": "leaf",
                    "input": {},
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="END")],
                }
            },
        }
    )
    selfish = parse_machine(
        {
            "machine": "selfish",
            "entry": "c",
            "budget": 3,
            "states": {
                "c": {
                    "call": "selfish",
                    "input": {},
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="END")],
                }
            },
        }
    )
    registry = {"leaf": leaf, "parent": parent, "selfish": selfish}
    assert machine_touches_tools(parent, registry) is True
    assert machine_touches_tools(selfish, registry) is False  # recursion terminates
    assert machine_touches_tools(None, registry) is False


def test_invalid_policy_is_rejected():
    with pytest.raises(ValueError, match="on_untrusted_flow"):
        go(machine(), policy="ignore")
