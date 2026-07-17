"""Session persistence (ADR 0015 M2c): roundtrip, latest, transcript, --continue."""

import asyncio
import json

import pytest

from mklang.console.session import Session

pytest.importorskip("textual")

from mklang.console.app import build_app
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM

CONFIG = "config/runtime.example.yaml"


def test_session_roundtrip(tmp_path):
    s = Session.create(tmp_path, workspace="/ws", brain="console_agent")
    assert (s.dir / "state.json").is_file() and s.checkpoints_dir.is_dir()
    s.history = "user: hi\nagent: hello"
    s.spent_in, s.spent_out = 10, 5
    s.consented = ["calc"]
    s.save_state()
    s.append({"t": "user", "text": "hi"})
    s.append({"t": "agent", "text": "hello"})

    loaded = Session.load(s.dir)
    assert loaded.history == s.history
    assert (loaded.spent_in, loaded.spent_out) == (10, 5)
    assert loaded.consented == ["calc"]
    lines = (s.dir / "transcript.jsonl").read_text().strip().splitlines()
    assert [json.loads(line)["t"] for line in lines] == ["user", "agent"]


def test_latest_picks_newest_and_handles_empty(tmp_path):
    assert Session.latest(tmp_path / "nowhere") is None
    a = Session.create(tmp_path)
    b = Session.create(tmp_path)
    assert Session.latest(tmp_path).id == max(a.id, b.id)


def reply_llm():
    def produce_fn(model, system, user, reason):
        if "single next action" in user:
            return Produced(text="REPLY: ok", input_tokens=7, output_tokens=3)
        return Produced(text="done!", input_tokens=2, output_tokens=1)

    return MockLLM(produce_fn=produce_fn, judge_fn=lambda *a: 4)


def loop_llm():
    """decide always chooses DISCOVER → the turn burns its whole step budget."""

    def produce_fn(model, system, user, reason):
        return Produced(text="DISCOVER: keep looking.")

    return MockLLM(produce_fn=produce_fn, judge_fn=lambda *a: 0)


def test_budget_exhaustion_parks_a_checkpoint_on_decline(tmp_path):
    base = str(tmp_path / "sessions")
    app = build_app(
        CONFIG,
        None,
        str(tmp_path / "ws"),
        build_llm=lambda prov: loop_llm(),
        session_base=base,
    )

    async def drive():
        from textual.widgets import Input

        async with app.run_test() as pilot:
            await pilot.click("#prompt")
            await pilot.press(*"loop forever")
            await pilot.press("enter")
            for _ in range(200):  # wait for the budget confirm to open the input
                await pilot.pause(0.05)
                if app.answer_mode:
                    break
            assert app.answer_mode, "budget confirm never reached the UI"
            await pilot.press("n")
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.05)
                if not app.query_one("#prompt", Input).disabled:
                    break
            cks = list(app.session.checkpoints_dir.glob("turn-*.json"))
            assert len(cks) == 1
            ck = json.loads(cks[0].read_text())
            assert ck["reason"] == "budget-exhausted" and ck["frames"]

    asyncio.run(drive())


def park_then_reply_llm():
    """Loops on DISCOVER until the judge script flips to REPLY (post-resume)."""
    judges = [0] * 8 + [4]

    def produce_fn(model, system, user, reason):
        if "final reply" in user:
            return Produced(text="resumed and finished.")
        return Produced(text="DISCOVER: still looking.")

    def judge_fn(model, conditions, output, context, reasoning=None):
        return judges.pop(0) if len(judges) > 1 else judges[0]

    return MockLLM(produce_fn=produce_fn, judge_fn=judge_fn)


def test_slash_resume_finishes_a_parked_turn(tmp_path):
    from textual.widgets import Input

    app = build_app(
        CONFIG,
        None,
        str(tmp_path / "ws"),
        build_llm=lambda prov: park_then_reply_llm(),
        session_base=str(tmp_path / "sessions"),
    )

    async def drive():
        async with app.run_test() as pilot:
            await pilot.click("#prompt")
            await pilot.press(*"loop then reply")
            await pilot.press("enter")
            for _ in range(200):
                await pilot.pause(0.05)
                if app.answer_mode:
                    break
            await pilot.press("n")  # decline: park the checkpoint
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.05)
                if not app.query_one("#prompt", Input).disabled:
                    break

            await pilot.click("#prompt")
            await pilot.press(*"/resume")
            await pilot.press("enter")
            await pilot.pause(0.1)
            assert any("[0]" in line for line in app.log_history)

            await pilot.press(*"/resume 0")
            await pilot.press("enter")
            for _ in range(200):
                await pilot.pause(0.05)
                if "agent: resumed and finished." in "\n".join(app.log_history):
                    break
            assert any("resumed and finished." in line for line in app.log_history)

    asyncio.run(drive())


def test_continue_restores_history_and_spend(tmp_path):
    base = str(tmp_path / "sessions")

    async def first():
        app = build_app(
            CONFIG,
            None,
            str(tmp_path / "ws"),
            build_llm=lambda prov: reply_llm(),
            session_base=base,
        )
        async with app.run_test() as pilot:
            await pilot.click("#prompt")
            await pilot.press(*"hello")
            await pilot.press("enter")
            from textual.widgets import Input

            for _ in range(100):
                await pilot.pause(0.05)
                if not app.query_one("#prompt", Input).disabled:
                    break
            return app.session.id, app.spent_in, app.spent_out

    sid, tin, tout = asyncio.run(first())
    assert (tin, tout) == (9, 4)  # decide 7+3, reply 2+1

    async def second():
        app = build_app(
            CONFIG,
            None,
            str(tmp_path / "ws"),
            build_llm=lambda prov: reply_llm(),
            session_base=base,
            continue_session=True,
        )
        async with app.run_test() as pilot:
            await pilot.pause(0.1)
            return app.session.id, app.history, app.spent_in, app.spent_out

    sid2, history, rin, rout = asyncio.run(second())
    assert sid2 == sid
    assert "user: hello" in history and "agent: done!" in history
    assert (rin, rout) == (9, 4)
