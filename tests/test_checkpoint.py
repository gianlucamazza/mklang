"""Suspend/resume checkpoint semantics against a MockLLM (ADR 0007)."""

import json

from mklang import cli
from mklang.checkpoint import (
    decode_repair,
    encode_repair,
    load_checkpoint,
    save_checkpoint,
    verify_hash,
)
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


def costly():
    """Every produce spends 15 tokens (10 in + 5 out) to drive the cost pool."""
    return MockLLM(produce_fn=lambda *a: Produced(text="ok", input_tokens=10, output_tokens=5))


def state(to):
    return {
        "structure": "s",
        "prompt": "p",
        "output": f"o_{to}",
        "gates": [gate("otherwise", then="ok", to=to)],
    }


def linear3():
    return M(
        {
            "machine": "lin",
            "entry": "a",
            "budget": 10,
            "states": {"a": state("b"), "b": state("c"), "c": state("END")},
        }
    )


def test_root_suspend_on_cost():
    m = linear3()
    r = run1(m, costly(), cost_budget=20, suspendable=True)
    assert r.status == "suspended"
    assert r.error == "cost-exhausted"
    assert r.at == "c"
    assert len(r.frames) == 1
    f = r.frames[0]
    assert f["machine"] == "lin" and f["state"] == "c" and f["steps"] == 2
    assert f["total_in"] == 20 and f["total_out"] == 10
    assert [s["state"] for s in f["trace"]] == ["a", "b"]
    json.dumps(r.frames)  # the payload must be JSON-safe end-to-end


def test_golden_round_trip():
    full = run1(linear3(), costly())
    r = run1(linear3(), costly(), cost_budget=20, suspendable=True)
    assert r.status == "suspended"
    frames = json.loads(json.dumps(r.frames))  # simulate the file round-trip
    done = run1(linear3(), costly(), resume=frames, suspendable=True)
    assert done.status == "done"
    assert (done.result, done.trace, done.usage, done.context) == (
        full.result,
        full.trace,
        full.usage,
        full.context,
    )


def _nested():
    sub = M(
        {
            "machine": "sub",
            "entry": "s1",
            "budget": 10,
            "result": "o_s3",
            "states": {"s1": state("s2"), "s2": state("s3"), "s3": state("END")},
        }
    )
    par = M(
        {
            "machine": "par",
            "entry": "c1",
            "budget": 10,
            "states": {
                "c1": {
                    "structure": "s",
                    "call": "sub",
                    "output": "sub_out",
                    "gates": [gate("otherwise", then="ok", to="z")],
                },
                "z": state("END"),
            },
        }
    )
    return par, {"par": par, "sub": sub}


def test_nested_call_suspend_and_resume():
    par, reg = _nested()
    full = run1(par, costly(), registry=reg, cost_budget=100, suspendable=True)
    assert full.status == "done"

    r = run1(par, costly(), registry=reg, cost_budget=20, suspendable=True)
    assert r.status == "suspended"
    assert r.error == "cost-exhausted"
    assert len(r.frames) == 2
    assert r.frames[0]["machine"] == "par" and r.frames[0]["state"] == "c1"
    assert r.frames[1]["machine"] == "sub" and r.frames[1]["state"] == "s3"
    assert r.at == "s3"
    # Parent totals exclude the sub's partial spend (added only when the call completes).
    assert r.frames[0]["total_in"] == 0 and r.frames[0]["steps"] == 0
    assert r.frames[1]["total_in"] == 20

    frames = json.loads(json.dumps(r.frames))
    done = run1(par, costly(), registry=reg, resume=frames, cost_budget=100, suspendable=True)
    assert done.status == "done"
    assert (done.result, done.trace, done.usage, done.context) == (
        full.result,
        full.trace,
        full.usage,
        full.context,
    )


def test_repair_round_trip():
    def repair_machine():
        return M(
            {
                "machine": "r",
                "entry": "a",
                "budget": 10,
                "states": {
                    "a": {
                        "structure": "s",
                        "prompt": "p",
                        "output": "o",
                        "gates": [gate("done", then="ok", to="END"), gate("fix", repair=2, to="a")],
                    },
                },
            }
        )

    def pick_fix_if_present(model, conditions, *a):
        # Prefer the repair condition while eligible; once exhausted only "done" remains.
        for i, c in enumerate(conditions):
            if c == "fix":
                return i
        return 0

    full = run1(
        repair_machine(), MockLLM(produce_fn=costly()._produce, judge_fn=pick_fix_if_present)
    )
    assert [s["policy"] for s in full.trace] == ["repair", "repair", "ok"]

    r = run1(
        repair_machine(),
        MockLLM(produce_fn=costly()._produce, judge_fn=pick_fix_if_present),
        cost_budget=10,
        suspendable=True,
    )
    assert r.status == "suspended"
    f = r.frames[0]
    assert f["repair_left"] == [["a", 1, 1]]  # one of two repairs already spent
    assert "did not satisfy" in f["feedback"]
    assert decode_repair(f["repair_left"]) == {("a", 1): 1}

    frames = json.loads(json.dumps(r.frames))
    done = run1(
        repair_machine(),
        MockLLM(produce_fn=costly()._produce, judge_fn=pick_fix_if_present),
        resume=frames,
        suspendable=True,
    )
    assert done.status == "done"
    assert (done.trace, done.usage) == (full.trace, full.usage)


def test_step_budget_suspend_is_idempotent():
    m = M(
        {
            "machine": "sb",
            "entry": "a",
            "budget": 2,
            "states": {"a": state("b"), "b": state("c"), "c": state("END")},
        }
    )
    r = run1(m, costly(), suspendable=True)
    assert r.status == "suspended" and r.error == "budget-exhausted" and r.at == "c"
    again = run1(m, costly(), resume=json.loads(json.dumps(r.frames)), suspendable=True)
    assert again.status == "suspended" and again.error == "budget-exhausted"
    assert again.frames == r.frames


def test_fanout_branches_never_suspend():
    sub = M(
        {
            "machine": "sub",
            "entry": "s1",
            "budget": 10,
            "states": {"s1": state("s2"), "s2": state("END")},
        }
    )
    par = M(
        {
            "machine": "fo",
            "entry": "m",
            "budget": 10,
            "context": {"items": [1, 2]},
            "states": {
                "m": {
                    "structure": "s",
                    "call": "sub",
                    "over": "{{items}}",
                    "output": "outs",
                    "gates": [gate("otherwise", then="ok", to="z")],
                },
                "z": state("END"),
            },
        }
    )
    r = run1(par, costly(), registry={"fo": par, "sub": sub}, cost_budget=10, suspendable=True)
    # Each branch's sub halts on cost and becomes a marker; the run suspends at the NEXT loop-top.
    assert r.trace[0]["branches"] == ["[branch-error: cost-exhausted]"] * 2
    assert r.status == "suspended" and r.at == "z"
    assert len(r.frames) == 1 and r.frames[0]["state"] == "z"


def test_suspendable_off_still_halts():
    r = run1(linear3(), costly(), cost_budget=20)
    assert r.status == "halt" and r.error == "cost-exhausted" and r.frames is None


def test_resume_mismatch_halts():
    m = linear3()
    r = run1(m, costly(), cost_budget=20, suspendable=True)
    bad = json.loads(json.dumps(r.frames))
    bad[0]["machine"] = "someone-else"
    out = run1(m, costly(), resume=bad, suspendable=True)
    assert out.status == "halt" and out.error.startswith("resume-mismatch")


MK = """\
machine: demo
entry: a
budget: 5
states:
  a:
    structure: s
    prompt: p
    output: o
    gates:
      - when: otherwise
        then: ok
        to: END
"""


def test_envelope_save_load_and_hash(tmp_path):
    mk = tmp_path / "demo.mk"
    mk.write_text(MK, encoding="utf-8")
    ck_path = tmp_path / "ck.json"
    frames = [
        {
            "machine": "demo",
            "state": "a",
            "ctx": {},
            "steps": 0,
            "total_in": 0,
            "total_out": 0,
            "feedback": "",
            "repair_left": [],
            "trace": [],
        }
    ]
    save_checkpoint(ck_path, "demo", mk, "cost-exhausted", frames, 100)
    ck = load_checkpoint(ck_path)
    assert ck["machine"] == "demo" and ck["frames"] == frames and ck["cost_budget"] == 100
    assert verify_hash(ck, mk)
    mk.write_text(MK + "# touched\n", encoding="utf-8")
    assert not verify_hash(ck, mk)
    assert encode_repair(decode_repair([["a", 1, 2]])) == [["a", 1, 2]]


def test_checkpoint_written_owner_only(tmp_path):
    """A checkpoint holds the full blackboard in plaintext — it must be 0600 (F5)."""
    import os
    import stat

    import pytest

    if os.name == "nt":  # POSIX permission bits are not meaningful on Windows
        pytest.skip("POSIX permissions only")
    mk = tmp_path / "demo.mk"
    mk.write_text(MK, encoding="utf-8")
    ck_path = tmp_path / "ck.json"
    # Pre-create with wide permissions to prove save_checkpoint tightens them.
    ck_path.write_text("{}", encoding="utf-8")
    os.chmod(ck_path, 0o644)
    save_checkpoint(ck_path, "demo", mk, "escalated", [], 100)
    assert stat.S_IMODE(os.stat(ck_path).st_mode) == 0o600


def test_cli_resume_guards(tmp_path, capsys, monkeypatch):
    mk = tmp_path / "demo.mk"
    mk.write_text(MK, encoding="utf-8")
    ck_path = tmp_path / "ck.json"
    frames = [
        {
            "machine": "demo",
            "state": "a",
            "ctx": {},
            "steps": 0,
            "total_in": 0,
            "total_out": 0,
            "feedback": "",
            "repair_left": [],
            "trace": [],
        }
    ]
    save_checkpoint(ck_path, "demo", mk, "cost-exhausted", frames, 100)

    # Not a checkpoint → exit 2
    junk = tmp_path / "junk.json"
    junk.write_text("{}", encoding="utf-8")
    assert cli.main(["resume", str(junk)]) == 2

    # Machine edited after checkpoint → exit 2 with a clear message, before any provider setup
    mk.write_text(MK + "# touched\n", encoding="utf-8")
    assert cli.main(["resume", str(ck_path)]) == 2
    assert "machine changed since checkpoint" in capsys.readouterr().err

    # --force gets past the hash check (stub _prepare to avoid provider/config setup)
    monkeypatch.setattr(cli, "_prepare", lambda *a: 99)
    assert cli.main(["resume", str(ck_path), "--force"]) == 99
