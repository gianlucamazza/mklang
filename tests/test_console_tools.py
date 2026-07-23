"""Console tools (ADR 0015 M1b): bridge-injected, workspace-confined, offline."""

import json
import re

import pytest

from mklang.console.tools import ConsoleTools
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM

CONFIG = "config/runtime.example.yaml"

HITL_SRC = """\
mklang: "0.3"
machine: approval
entry: draft
budget: 6
result: final
context:
  request: ""
states:
  draft:
    structure: a decision that grants the request
    prompt: "grant: {{request}}"
    output: draft
    gates:
      - when: the decision grants something
        escalate: true
        to: review
      - when: otherwise
        then: ok
        to: END
  review:
    structure: the human decision applied
    prompt: "human said {{human.reply}}"
    output: final
    gates:
      - when: otherwise
        then: ok
        to: END
"""

TOOLY_SRC = """\
mklang: "0.3"
machine: tooly
entry: c
budget: 4
result: out
context:
  expr: "1+1"
states:
  c:
    tool: calc
    input: { expression: "{{expr}}" }
    output: out
    gates:
      - when: otherwise
        then: ok
        to: END
"""


class FakeBridge:
    def __init__(self, reply="approved", yes=True):
        self.events = []
        self.questions = []
        self.confirms = []
        self.reply = reply
        self.yes = yes

    def emit(self, event):
        self.events.append(event)

    def ask(self, question):
        self.questions.append(question)
        return self.reply

    def confirm(self, prompt):
        self.confirms.append(prompt)
        return self.yes


def echo_llm(prov=None, judge=0):
    return MockLLM(
        produce_fn=lambda model, system, user, reason: Produced(text=user),
        judge_fn=lambda *a: judge,
    )


@pytest.fixture
def tools(tmp_path):
    return ConsoleTools(
        config=CONFIG,
        provider=None,
        bridge=FakeBridge(),
        workspace=tmp_path / "ws",
        build_llm=echo_llm,
    )


def test_tool_registry_names(tools):
    assert set(tools.as_tool_registry()) == {
        "list_machines",
        "describe_machine",
        "read_machine",
        "check_machine",
        "write_machine",
        "run_machine",
        "ask_user",
    }


def test_close_is_optional_and_idempotent(tmp_path):
    class ClosableLLM(MockLLM):
        def __init__(self):
            super().__init__()
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    llm = ClosableLLM()
    closable = ConsoleTools(
        config=CONFIG,
        provider=None,
        bridge=FakeBridge(),
        workspace=tmp_path / "closable",
        build_llm=lambda prov: llm,
    )
    closable.close()
    closable.close()
    assert llm.close_calls == 1

    tools_without_close = ConsoleTools(
        config=CONFIG,
        provider=None,
        bridge=FakeBridge(),
        workspace=tmp_path / "no-close",
        build_llm=echo_llm,
    )
    tools_without_close.close()


def test_list_and_describe_include_workspace_machines(tools):
    (tools.workspace / "approval.mk").write_text(HITL_SRC, encoding="utf-8")
    listed = json.loads(tools.list_machines({}))
    names = {m["name"] for m in listed["machines"]}
    assert "std_cot" in names and "approval" in names
    desc = json.loads(tools.describe_machine({"name": "approval"}))
    assert desc["result"] == "final"
    unknown = json.loads(tools.describe_machine({"name": "ghost"}))
    assert "unknown machine" in unknown["error"]


def test_write_machine_is_workspace_confined(tools):
    refused = json.loads(tools.write_machine({"name": "../evil", "source": "x"}))
    assert "escapes the workspace" in refused["error"]
    assert not (tools.workspace.parent / "evil.mk").exists()

    ok = json.loads(tools.write_machine({"name": "approval", "source": HITL_SRC}))
    assert ok["written"] == "approval.mk"
    assert ok["check"]["ok"] is True

    tools.bridge.yes = False  # decline overwrite
    declined = json.loads(tools.write_machine({"name": "approval", "source": "machine: x"}))
    assert "declined" in declined["error"]
    assert "approval" in (tools.workspace / "approval.mk").read_text()


def test_write_machine_derives_name_from_source(tools):
    ok = json.loads(tools.write_machine({"source": HITL_SRC}))
    assert ok["written"] == "approval.mk"
    assert (tools.workspace / "approval.mk").is_file()

    bad_yaml = json.loads(tools.write_machine({"source": "states: [unclosed"}))
    assert "not valid YAML" in bad_yaml["error"]
    nameless = json.loads(tools.write_machine({"source": "entry: a\nbudget: 3"}))
    assert "no `machine:` name" in nameless["error"]


def test_check_machine_reports_errors(tools):
    bad = json.loads(
        tools.check_machine(
            {
                "source": "machine: x\nentry: gone\nbudget: 2\nstates:\n  s: {structure: s, prompt: p, output: o, gates: [{when: otherwise, then: ok, to: END}]}\n"
            }
        )
    )
    assert bad["ok"] is False
    assert any("entry 'gone'" in e for e in bad["errors"])


def test_run_machine_by_name_and_events_flow(tools):
    out = json.loads(tools.run_machine({"target": "std_cot", "inputs": '{"task": "2+2?"}'}))
    assert out["status"] == "done"
    kinds = [e["type"] for e in tools.bridge.events]
    assert "run-start" in kinds and "state-done" in kinds
    assert all(e["run"] == "std_cot" for e in tools.bridge.events)


def test_run_machine_hitl_brokered_to_bridge(tools):
    (tools.workspace / "approval.mk").write_text(HITL_SRC, encoding="utf-8")
    out = json.loads(tools.run_machine({"target": "approval", "inputs": '{"request": "refund"}'}))
    assert out["status"] == "done"
    assert "approved" in out["result"]
    assert len(tools.bridge.questions) == 1
    assert "escalated at review" in tools.bridge.questions[0]


def test_run_machine_tool_consent(tools):
    (tools.workspace / "tooly.mk").write_text(TOOLY_SRC, encoding="utf-8")
    out = json.loads(tools.run_machine({"target": "tooly", "inputs": "{}"}))
    assert out["status"] == "done"
    assert any("calc" in c for c in tools.bridge.confirms)
    # consent is remembered: a second run does not ask again
    n = len(tools.bridge.confirms)
    tools.run_machine({"target": "tooly", "inputs": "{}"})
    assert len(tools.bridge.confirms) == n


WRITY_SRC = """\
mklang: "0.3"
machine: writy
entry: w
budget: 4
result: out
states:
  w:
    tool: write_file
    input: { path: "report.md", content: "done" }
    output: out
    gates:
      - when: otherwise
        then: ok
        to: END
"""


def test_run_machine_consent_grants_fs_writes(tools, tmp_path):
    from mklang import fs

    fs.configure_fs(fs.LocalFSBackend(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    assert fs.writes_allowed() is False
    (tools.workspace / "writy.mk").write_text(WRITY_SRC, encoding="utf-8")
    out = json.loads(tools.run_machine({"target": "writy", "inputs": "{}"}))
    assert out["status"] == "done"
    assert any("write_file" in c for c in tools.bridge.confirms)
    assert fs.writes_allowed() is True
    assert (tmp_path / "data" / "report.md").read_text(encoding="utf-8") == "done"


def test_run_machine_tool_consent_declined(tmp_path):
    tools = ConsoleTools(
        config=CONFIG,
        provider=None,
        bridge=FakeBridge(yes=False),
        workspace=tmp_path / "ws",
        build_llm=echo_llm,
    )
    (tools.workspace / "tooly.mk").write_text(TOOLY_SRC, encoding="utf-8")
    out = json.loads(tools.run_machine({"target": "tooly", "inputs": "{}"}))
    assert "declined" in out["error"]


def test_run_machine_bad_inputs_and_unknown_target(tools):
    assert (
        "not valid JSON"
        in json.loads(tools.run_machine({"target": "std_cot", "inputs": "{oops"}))["error"]
    )
    assert "unknown machine" in json.loads(tools.run_machine({"target": "nope"}))["error"]


def test_ask_user_passthrough(tools):
    assert tools.ask_user({"question": "which env?"}) == "approved"
    assert tools.bridge.questions[-1] == "which env?"


def test_run_machine_observation_propagates_produce_truncation(tools):
    """ADR 0018 signal must reach the brain — not only the inner trace."""
    long_src = """\
mklang: "0.3"
machine: longy
entry: a
budget: 4
result: out
context: {}
states:
  a:
    structure: long text
    prompt: "write a lot"
    output: out
    gates:
      - when: otherwise
        then: ok
        to: END
"""
    (tools.workspace / "longy.mk").write_text(long_src, encoding="utf-8")

    def truncating_llm(prov=None):
        return MockLLM(
            produce_fn=lambda model, system, user, reason: Produced(
                text="partial answer that was cut",
                truncated=True,
                finish_reason="length",
            )
        )

    tools.build_llm = truncating_llm
    tools.llm = truncating_llm()
    out = json.loads(tools.run_machine({"target": "longy", "inputs": "{}"}))
    assert out["status"] == "done"
    assert out["truncated"] is True
    assert out["finish_reason"] == "length"
    assert out["trace"]["truncated"] is True
    assert out["trace"]["truncated_steps"][0]["state"] == "a"


def test_run_machine_observation_marks_result_clip_honestly(tools):
    long_src = """\
mklang: "0.3"
machine: big
entry: a
budget: 4
result: out
context: {}
states:
  a:
    structure: long text
    prompt: "pad"
    output: out
    gates:
      - when: otherwise
        then: ok
        to: END
"""
    (tools.workspace / "big.mk").write_text(long_src, encoding="utf-8")
    blob = "Z" * 2500

    def long_llm(prov=None):
        return MockLLM(produce_fn=lambda model, system, user, reason: Produced(text=blob))

    tools.build_llm = long_llm
    tools.llm = long_llm()
    out = json.loads(tools.run_machine({"target": "big", "inputs": "{}"}))
    assert out["result_truncated"] is True
    assert out["result_full_chars"] == 2500
    assert out["result"].endswith("…[truncated]")
    assert len(out["result"]) == 2000
    # produce itself was complete — only the observation budget clipped
    assert out["truncated"] is False


def test_run_machine_injects_declared_today(tools):
    src = """\
mklang: "0.3"
machine: dated
entry: a
budget: 4
result: out
context:
  today: ""
states:
  a:
    structure: the date
    prompt: "today is {{today}}"
    output: out
    gates:
      - when: otherwise
        then: ok
        to: END
"""
    (tools.workspace / "dated.mk").write_text(src, encoding="utf-8")
    out = json.loads(tools.run_machine({"target": "dated", "inputs": "{}"}))
    assert out["status"] == "done"
    # echo_llm returns the user prompt; the injected date is host-supplied,
    # so it interpolates fenced (ADR 0025). ISO year prefix inside the fence.
    assert re.search(r"today is <data-\w+>\n20", out["result"])


def test_run_machine_injects_declared_now(tools):
    src = """\
mklang: "0.3"
machine: clocked
entry: a
budget: 4
result: out
context:
  now: ""
states:
  a:
    structure: the time
    prompt: "now is {{now}}"
    output: out
    gates:
      - when: otherwise
        then: ok
        to: END
"""
    (tools.workspace / "clocked.mk").write_text(src, encoding="utf-8")
    out = json.loads(tools.run_machine({"target": "clocked", "inputs": "{}"}))
    assert out["status"] == "done"
    assert re.search(r"now is <data-\w+>\n20", out["result"])
    assert "T" in out["result"]
