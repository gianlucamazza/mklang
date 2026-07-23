"""The MCP server surface (ADR 0011): run/resume tools, HITL round-trip, error payloads."""

import asyncio
import json
import re
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.mcp import server as srv
from mklang.mcp.sessions import SessionStore

DEFAULTS = {"config": "config/runtime.example.yaml", "provider": None}


def test_main_binds_workspace_flags_before_serving(tmp_path, monkeypatch, capsys):
    from mklang import fs

    assert srv.main(["--workspace", str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err

    def _no_server(*args, **kwargs):
        raise ImportError  # stop before the blocking stdio loop

    monkeypatch.setattr(srv, "create_server", _no_server)
    assert srv.main(["--workspace", str(tmp_path), "--allow-write", "--log-level", "debug"]) == 2
    backend = fs.current_fs_backend()
    assert isinstance(backend, fs.LocalFSBackend) and backend.root == tmp_path.resolve()
    assert fs.writes_allowed() is True
    import logging

    from mklang.logs import setup_process_logging

    assert logging.getLogger("mklang").getEffectiveLevel() == logging.DEBUG
    setup_process_logging(None)  # restore the suite default


def test_server_default_config_uses_the_resolution_chain():
    # None means load_provider walks the full ADR 0021 chain (project > user >
    # /etc > bundled) — the server must not pin the checkout-relative example.
    assert srv.DEFAULT_CONFIG is None


HITL = """\
machine: h
entry: draft
budget: 10
result: final
states:
  draft:
    structure: s
    prompt: write the draft
    output: draft
    gates:
      - when: looks risky
        escalate: true
        to: review
      - when: otherwise
        then: ok
        to: END
  review:
    structure: s
    prompt: "apply the human decision: {{human.reply}}"
    output: final
    gates:
      - when: otherwise
        then: ok
        to: END
"""

LINEAR = """\
machine: lin
entry: a
budget: 10
result: r3
states:
  a:
    structure: s
    prompt: one
    output: r1
    gates: [{when: otherwise, then: ok, to: b}]
  b:
    structure: s
    prompt: two
    output: r2
    gates: [{when: otherwise, then: ok, to: c}]
  c:
    structure: s
    prompt: three
    output: r3
    gates: [{when: otherwise, then: ok, to: END}]
"""


def echo_llm(judge=0):
    return MockLLM(
        produce_fn=lambda model, system, user, reason: Produced(text=user),
        judge_fn=lambda *a: judge,
    )


def costly_llm():
    """Every produce spends 15 tokens, so a cost budget of 20 suspends mid-run."""
    return MockLLM(
        produce_fn=lambda *a: Produced(text="ok", input_tokens=10, output_tokens=5),
        judge_fn=lambda *a: 0,
    )


@pytest.fixture
def store():
    return SessionStore()


def use_llm(monkeypatch, factory):
    monkeypatch.setattr(srv, "_build_llm", lambda prov: factory())


def test_run_inline_source_done(monkeypatch, store):
    use_llm(monkeypatch, echo_llm)
    out = srv.run_tool(store, DEFAULTS, source=LINEAR)
    assert out["status"] == "done"
    assert out["result"] == "three"
    assert out["trace"] and out["usage"] is not None
    assert "checkpoint" not in out


def test_run_inputs_reach_context(monkeypatch, store):
    use_llm(monkeypatch, echo_llm)
    src = LINEAR.replace("prompt: one", 'prompt: "q={{ticket.body}}"').replace(
        "result: r3", "result: r1"
    )
    out = srv.run_tool(store, DEFAULTS, source=src, inputs={"ticket.body": "hello"})
    assert out["status"] == "done"
    # MCP inputs are host-supplied → tainted → fenced in the prompt (ADR 0025).
    assert re.search(r"q=<data-\w+>\nhello\n</data-\w+>", out["result"])


def test_run_requires_exactly_one_of_source_and_path(store):
    both = srv.run_tool(store, DEFAULTS, source=HITL, path="examples/triage.mkl")
    neither = srv.run_tool(store, DEFAULTS)
    assert both["status"] == neither["status"] == "error"
    assert both["error"] == neither["error"] == "invalid-request"


def test_on_truncate_halt_parity(monkeypatch, store):
    """MCP exposes the same on_truncate=halt policy as the CLI (ADR 0018)."""

    def truncating():
        return MockLLM(
            produce_fn=lambda *a: Produced(text="cut", truncated=True, finish_reason="length"),
            judge_fn=lambda *a: 0,
        )

    use_llm(monkeypatch, truncating)
    out = srv.run_tool(store, DEFAULTS, source=LINEAR, on_truncate="halt")
    assert out["status"] == "halt"
    assert out["error"] == "state-error: output-truncated"


def test_on_truncate_invalid_is_error_payload(store):
    out = srv.run_tool(store, DEFAULTS, source=LINEAR, on_truncate="continue")
    assert out["status"] == "error"
    assert out["error"] == "invalid-request"


def test_run_invalid_source_is_error_payload(monkeypatch, store):
    use_llm(monkeypatch, echo_llm)
    out = srv.run_tool(store, DEFAULTS, source="states: [unclosed")
    assert out["status"] == "error"
    assert out["error"] == "prepare-failed"
    assert "invalid YAML" in out["errors"][0]


def test_run_inline_call_to_unsupplied_machine_is_semantic_error(monkeypatch, store):
    use_llm(monkeypatch, echo_llm)
    caller = (
        "machine: caller\nentry: c\nbudget: 3\nstates:\n  c:\n    call: ghost\n"
        "    output: sub\n    gates: [{when: otherwise, then: ok, to: END}]\n"
    )
    out = srv.run_tool(store, DEFAULTS, source=caller)
    assert out["status"] == "error"
    assert any("unknown machine 'ghost'" in e for e in out["errors"])


def test_hitl_suspend_resume_roundtrip(monkeypatch, store):
    use_llm(monkeypatch, echo_llm)
    out = srv.run_tool(store, DEFAULTS, source=HITL, hitl=True)
    assert out["status"] == "suspended"
    assert out["error"] == "escalated"
    handle = out["checkpoint"]
    assert store.get(handle) is not None

    done = srv.resume_tool(store, handle, inputs={"human.reply": "approve"})
    assert done["status"] == "done"
    assert "approve" in done["result"]
    # the handle is single-use
    again = srv.resume_tool(store, handle)
    assert again["status"] == "error"
    assert again["error"] == "unknown-checkpoint"


def test_cost_suspend_and_resume_with_raised_budget(monkeypatch, store):
    use_llm(monkeypatch, costly_llm)
    out = srv.run_tool(store, DEFAULTS, source=LINEAR, cost_budget=20)
    assert out["status"] == "suspended"
    assert out["error"] == "cost-exhausted"
    h1 = out["checkpoint"]

    # not raising the budget re-suspends immediately, with a warning and a NEW handle
    stuck = srv.resume_tool(store, h1)
    assert stuck["status"] == "suspended"
    assert any("not above the exhausted" in w for w in stuck["warnings"])
    h2 = stuck["checkpoint"]
    assert h2 != h1
    assert store.get(h1) is None

    done = srv.resume_tool(store, h2, cost_budget=100)
    assert done["status"] == "done"
    assert done["result"] == "ok"


def test_run_by_path_examples(monkeypatch, store):
    use_llm(monkeypatch, echo_llm)
    out = srv.run_tool(store, DEFAULTS, path="examples/summarize_doc.mkl", inputs={"doc": "x"})
    assert out["status"] == "done"


def test_list_and_describe_machines(tmp_path, monkeypatch):
    # Isolate from the host: a real user/system machines dir must not leak in.
    monkeypatch.setenv("MKLANG_DATA_DIR", str(tmp_path / "data"))
    out = srv.list_machines_tool()
    names = [m["name"] for m in out["machines"]]
    assert "std_cot" in names and all(m["source"] == "stdlib" for m in out["machines"])
    desc = srv.describe_machine_tool("std_refine")
    assert desc["result"] == "answer"
    assert "criteria" in desc["context"]
    assert {s["id"] for s in desc["states"]} == {"draft", "flag_unresolved"}
    missing = srv.describe_machine_tool("nope")
    assert missing["status"] == "error" and missing["error"] == "unknown-machine"


def test_check_tool_structured_output():
    ok = srv.check_tool(path="examples/triage.mkl")
    assert ok["ok"] is True and ok["errors"] == []
    bad = srv.check_tool(
        source="machine: x\nentry: gone\nbudget: 2\nstates:\n  s:\n    structure: s\n    prompt: p\n    output: o\n    gates: [{when: otherwise, then: ok, to: END}]\n"
    )
    assert bad["ok"] is False
    assert any("entry 'gone' is not a state" in e for e in bad["errors"])
    both = srv.check_tool(source="x", path="y")
    assert both["status"] == "error" and both["error"] == "invalid-request"


def test_durable_resume_across_stores(monkeypatch, store, tmp_path):
    """run(checkpoint_path=…) → kill the store → resume from the FILE."""
    use_llm(monkeypatch, echo_llm)
    ck = str(tmp_path / "ck.json")
    out = srv.run_tool(store, DEFAULTS, source=HITL, hitl=True, checkpoint_path=ck)
    assert out["status"] == "suspended"
    assert out["checkpoint_file"] == ck

    fresh_store = SessionStore()  # a different process would have an empty store
    done = srv.resume_tool(fresh_store, ck, inputs={"human.reply": "approve"}, defaults=DEFAULTS)
    assert done["status"] == "done"
    assert "approve" in done["result"]


def test_durable_resume_of_cli_checkpoint(monkeypatch, store, tmp_path):
    """A file written by `mklang run --checkpoint` resumes through the MCP tool."""
    import json

    from mklang import cli

    # judge 1 is out of range for std_cascade's 1-condition batch → escalate → suspend
    monkeypatch.setattr(cli, "_build_llm", lambda prov: echo_llm(judge=1))
    ck = str(tmp_path / "cli-ck.json")
    rc = cli.main(["run", "std_cascade", "--set", "task=hard", "--checkpoint", ck, "--hitl"])
    assert rc == 3
    json.loads(Path(ck).read_text())  # valid envelope

    use_llm(monkeypatch, echo_llm)
    done = srv.resume_tool(store, ck, defaults=DEFAULTS)
    assert done["status"] == "done"


def test_live_events_stream_as_logging_notifications(monkeypatch):
    """ADR 0016: a run's engine events arrive as `mklang.event` log notifications."""
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    monkeypatch.setattr(srv, "_build_llm", lambda prov: echo_llm())
    server = srv.create_server()
    events = []

    async def on_log(params):
        if params.logger == "mklang.event":
            events.append(json.loads(params.data))

    async def drive():
        async with connect(server._mcp_server, logging_callback=on_log) as client:
            res = await client.call_tool("run", {"path": "std_cot", "inputs": {"task": "2+2?"}})
            body = res.structuredContent or json.loads(res.content[0].text)
            if "status" not in body and "result" in body:
                body = body["result"]
            assert body["status"] == "done"

    asyncio.run(drive())
    kinds = [e["type"] for e in events]
    assert kinds[0] == "run-start"
    assert "state-start" in kinds and "state-done" in kinds
    done = next(e for e in events if e["type"] == "state-done")
    assert done["machine"] == "std_cot" and done["state"] == "solve"


def test_protocol_smoke_inmemory():
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    server = srv.create_server()

    async def smoke():
        async with connect(server._mcp_server) as client:
            tools = await client.list_tools()
            assert sorted(t.name for t in tools.tools) == [
                "check",
                "describe_machine",
                "list_machines",
                "resume",
                "run",
            ]
            res = await client.call_tool("run", {})  # invalid-request domain payload
            payload = (
                res.structuredContent
                if res.structuredContent is not None
                else json.loads(res.content[0].text)
            )
            if "status" not in payload and "result" in payload:
                payload = payload["result"]
            assert payload["status"] == "error"

    asyncio.run(smoke())
