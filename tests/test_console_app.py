"""The console TUI skeleton (ADR 0015 M1d): headless Pilot + scripted LLM, no keys."""

import asyncio

import pytest

pytest.importorskip("textual")

from mklang.console.app import build_app, load_brain
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM

CONFIG = "config/runtime.example.yaml"


def scripted_llm(produce_map, judge_seq):
    seq = list(judge_seq)

    def produce_fn(model, system, user, reason):
        for key, text in produce_map.items():
            if key in user:
                return Produced(text=text)
        return Produced(text="ok")

    def judge_fn(model, conditions, output, context, reasoning=None):
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return MockLLM(produce_fn=produce_fn, judge_fn=judge_fn)


def test_load_brain_is_the_bundled_agent():
    brain = load_brain()
    assert brain.name == "console_agent"
    assert brain.result == "reply"


async def _wait_input_enabled(app, pilot, timeout=5.0):
    from textual.widgets import Input

    for _ in range(int(timeout / 0.05)):
        await pilot.pause(0.05)
        if not app.query_one("#prompt", Input).disabled:
            return
    raise AssertionError("input never re-enabled — turn did not finish")


def test_direct_reply_turn(tmp_path):
    llm = scripted_llm(
        {"single next action": "REPLY: it is 4.", "final reply": "4."},
        [3],
    )
    app = build_app(CONFIG, None, str(tmp_path / "ws"), build_llm=lambda prov: llm)

    async def drive():
        async with app.run_test() as pilot:
            await pilot.click("#prompt")
            await pilot.press(*"2+2?")
            await pilot.press("enter")
            await _wait_input_enabled(app, pilot)
            assert "agent: 4." in app.history
            assert "user: 2+2?" in app.history
            assert app.spent_in == 0  # MockLLM spends nothing

    asyncio.run(drive())


def test_clarify_turn_uses_answer_mode(tmp_path):
    llm = scripted_llm(
        {
            "single next action": "CLARIFY: staging or prod?",
            "final reply": "Done on staging.",
        },
        [2, 3],
    )
    app = build_app(CONFIG, None, str(tmp_path / "ws"), build_llm=lambda prov: llm)

    async def drive():
        from textual.widgets import Input

        async with app.run_test() as pilot:
            await pilot.click("#prompt")
            await pilot.press(*"deploy it")
            await pilot.press("enter")
            for _ in range(100):  # wait for the HITL question to open the input
                await pilot.pause(0.05)
                if app.answer_mode:
                    break
            assert app.answer_mode, "ask_user never reached the UI"
            assert not app.query_one("#prompt", Input).disabled
            await pilot.press(*"staging")
            await pilot.press("enter")
            await _wait_input_enabled(app, pilot)
            assert "agent: Done on staging." in app.history

    asyncio.run(drive())
