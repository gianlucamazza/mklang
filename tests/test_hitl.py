"""Human-in-the-loop: escalate gates that suspend and resume on reply (ADR 0008)."""

import json
from pathlib import Path

from mklang import cli
from mklang.checkpoint import load_checkpoint
from mklang.engine import run
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def M(d):
    return parse_machine(d)


def run1(machine, llm, ctx=None, registry=None, **kw):
    reg = registry or {machine.name: machine}
    return run(
        machine, ctx if ctx is not None else dict(machine.context), reg, llm, TIERS, "m", **kw
    )


def gate(when, **kw):
    return {"when": when, **kw}


def echo_llm(judge=0):
    """produce echoes the user prompt (so tests can see interpolated replies)."""
    return MockLLM(
        produce_fn=lambda model, system, user, reason: Produced(text=user),
        judge_fn=lambda *a: judge,
    )


def hitl_machine():
    return M(
        {
            "machine": "h",
            "entry": "draft",
            "budget": 10,
            "result": "final",
            "states": {
                "draft": {
                    "structure": "s",
                    "prompt": "write the draft",
                    "output": "draft",
                    "gates": [
                        gate("looks risky", escalate=True, to="review"),
                        gate("otherwise", then="ok", to="END"),
                    ],
                },
                "review": {
                    "structure": "s",
                    "prompt": "apply the human decision: {{human.reply}}",
                    "output": "final",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )


def test_escalate_suspends_before_handler():
    r = run1(hitl_machine(), echo_llm(), escalate_suspend=True)
    assert r.status == "suspended" and r.error == "escalated"
    assert r.at == "review"
    assert len(r.frames) == 1
    f = r.frames[0]
    assert f["state"] == "review" and f["steps"] == 1
    assert r.trace[-1]["policy"] == "escalate" and r.trace[-1]["to"] == "review"
    json.dumps(r.frames)


def test_reply_injection_round_trip():
    r = run1(hitl_machine(), echo_llm(), escalate_suspend=True)
    frames = json.loads(json.dumps(r.frames))
    frames[-1]["ctx"]["human"] = {"reply": "approve with edits"}
    done = run1(hitl_machine(), echo_llm(), resume=frames, escalate_suspend=True)
    assert done.status == "done"
    assert "approve with edits" in done.result  # review prompt echoed by the mock
    assert [s["state"] for s in done.trace] == ["draft", "review"]


def test_escalate_routes_normally_by_default():
    r = run1(hitl_machine(), echo_llm())
    assert r.status == "done"
    assert [s["policy"] for s in r.trace] == ["escalate", "ok"]


def test_nested_escalate_unwinds_and_resumes():
    sub = hitl_machine()
    par = M(
        {
            "machine": "par",
            "entry": "c1",
            "budget": 10,
            "states": {
                "c1": {
                    "structure": "s",
                    "call": "h",
                    "output": "sub_out",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    reg = {"par": par, "h": sub}
    r = run1(par, echo_llm(), registry=reg, escalate_suspend=True)
    assert r.status == "suspended" and r.error == "escalated"
    assert [f["machine"] for f in r.frames] == ["par", "h"]
    assert r.at == "review"

    frames = json.loads(json.dumps(r.frames))
    frames[-1]["ctx"]["human"] = {"reply": "ship it"}
    done = run1(par, echo_llm(), registry=reg, resume=frames, escalate_suspend=True)
    assert done.status == "done"
    assert "ship it" in done.context["sub_out"]


def test_escalate_to_end_completes():
    m = M(
        {
            "machine": "e",
            "entry": "a",
            "budget": 5,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [gate("otherwise", escalate=True, to="END")],
                },
            },
        }
    )
    r = run1(m, echo_llm(), escalate_suspend=True)
    assert r.status == "done" and r.frames is None


def test_escalate_inside_fanout_branch_never_suspends():
    sub = hitl_machine()
    par = M(
        {
            "machine": "fo",
            "entry": "m",
            "budget": 10,
            "context": {"items": [1, 2]},
            "states": {
                "m": {
                    "structure": "s",
                    "call": "h",
                    "over": "{{items}}",
                    "output": "outs",
                    "gates": [gate("otherwise", then="ok", to="END")],
                },
            },
        }
    )
    r = run1(par, echo_llm(), registry={"fo": par, "h": sub}, escalate_suspend=True)
    # Inside branches the escalate just routes to `review`, which halts on the
    # missing {{human.reply}} — a marker, never a suspension.
    assert r.status == "done"
    assert all(b.startswith("[branch-error:") or "human" in b for b in r.context["outs"])


MK = """\
mklang: "0.2"
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


def test_cli_hitl_defaults_the_checkpoint_to_the_state_root(tmp_path, monkeypatch, capsys):
    # ADR 0023: --hitl without --checkpoint suspends into the XDG state root.
    monkeypatch.setenv("MKLANG_STATE_DIR", str(tmp_path / "state"))
    mk = tmp_path / "h.mk"
    mk.write_text(MK, encoding="utf-8")
    monkeypatch.setattr(cli, "_build_llm", lambda prov: echo_llm())

    rc = cli.main(["run", str(mk), "--hitl"])
    assert rc == 3
    out = json.loads(capsys.readouterr().out)
    ck = Path(out["checkpoint"])
    assert ck.parent == tmp_path / "state" / "checkpoints" and ck.is_file()
    env = load_checkpoint(ck)
    assert env["reason"] == "escalated" and env["hitl"] is True


def test_cli_hitl_round_trip(tmp_path, monkeypatch, capsys):
    mk = tmp_path / "h.mk"
    mk.write_text(MK, encoding="utf-8")
    ck = tmp_path / "ck.json"
    monkeypatch.setattr(cli, "_build_llm", lambda prov: echo_llm())

    rc = cli.main(["run", str(mk), "--checkpoint", str(ck), "--hitl"])
    assert rc == 3
    env = load_checkpoint(ck)
    assert env["reason"] == "escalated" and env["hitl"] is True
    capsys.readouterr()

    rc = cli.main(["resume", str(ck), "--set", "human.reply=approve"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "done"
    assert "approve" in out["result"]
