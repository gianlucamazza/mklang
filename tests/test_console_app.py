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
        [4],
    )
    app = build_app(
        CONFIG,
        None,
        str(tmp_path / "ws"),
        build_llm=lambda prov: llm,
        session_base=str(tmp_path / "sessions"),
    )

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


def test_agent_reply_markdown_and_bracket_safety(tmp_path):
    """Agent prose is mirrored as Markdown source; brackets must not break the log."""
    reply = "Use **bold** and array[0]; ignore [b]injected[/b]."
    llm = scripted_llm(
        {"single next action": f"REPLY: {reply}", "final reply": reply},
        [4],
    )
    app = build_app(
        CONFIG,
        None,
        str(tmp_path / "ws"),
        build_llm=lambda prov: llm,
        session_base=str(tmp_path / "sessions"),
    )

    async def drive():
        async with app.run_test() as pilot:
            await pilot.click("#prompt")
            await pilot.press(*"format me")
            await pilot.press("enter")
            await _wait_input_enabled(app, pilot)
            assert f"agent: {reply}" in app.history
            # Plain mirror keeps the source markdown (audit + tests), not Rich tags.
            assert any("**bold**" in line and "array[0]" in line for line in app.log_history)
            assert any("[b]injected[/b]" in line for line in app.log_history)

    asyncio.run(drive())


def all_labels(node):
    out = [str(node.label)]
    for child in node.children:
        out.extend(all_labels(child))
    return out


def test_activity_tree_untrusted_labels_are_plain():
    """User title and LLM preview must not be interpreted as Rich markup."""
    from mklang.console.widgets import ActivityTree

    tree = ActivityTree()
    tree.new_turn("array[0] [b]injected[/b]")
    assert "array[0]" in str(tree._turn_node.label)
    assert "[b]injected[/b]" in str(tree._turn_node.label)

    tree.feed(
        {
            "type": "run-start",
            "machine": "weird[b]name",
            "depth": 0,
            "entry": "decide",
        }
    )
    tree.feed(
        {
            "type": "state-start",
            "machine": "weird[b]name",
            "depth": 0,
            "state": "decide",
            "kind": "generative",
            "tier": "reasoning",
        }
    )
    tree.feed(
        {
            "type": "state-done",
            "machine": "weird[b]name",
            "depth": 0,
            "state": "decide",
            "policy": "ok",
            "to": "reply",
            "output": "see **bold** and [b]tag[/b]",
            "truncated": True,
        }
    )
    labels = all_labels(tree.root)
    blob = "\n".join(labels)
    assert "weird[b]name" in blob
    assert "see **bold** and [b]tag[/b]" in blob


def test_activity_tree_leaf_states_are_not_vacuously_expandable():
    """Regression: Textual defaults allow_expand=True, so empty brain states
    showed a chevron that revealed nothing. Leaves stay non-expandable until
    they gain a nested run or an output preview."""
    from mklang.console.widgets import ActivityTree

    tree = ActivityTree()
    tree.new_turn("q")
    tree.feed(
        {
            "type": "run-start",
            "machine": "console_agent",
            "depth": 0,
            "entry": "decide",
        }
    )
    tree.feed(
        {
            "type": "state-start",
            "machine": "console_agent",
            "depth": 0,
            "state": "decide",
            "kind": "generative",
            "tier": "reasoning",
        }
    )
    decide = tree._state_nodes[(None, 0, "decide")]
    assert decide.allow_expand is False
    assert len(decide.children) == 0

    tree.feed(
        {
            "type": "state-done",
            "machine": "console_agent",
            "depth": 0,
            "state": "decide",
            "policy": "ok",
            "to": "reply",
            "output": "REPLY: hello",
        }
    )
    # Normal previews now live in the inspector; only exceptional/truncated
    # output expands the activity tree.
    assert decide.allow_expand is False
    assert len(decide.children) == 0


def test_activity_tree_and_inspector(tmp_path):
    from mklang.console.widgets import ActivityTree, Inspector

    llm = scripted_llm(
        {
            "single next action": "RUN: std_cot task 2+2",
            "run request JSON": '{"target": "std_cot", "inputs": {"task": "2+2"}}',
            "final reply": "4.",
        },
        [1, 4],
    )
    app = build_app(
        CONFIG,
        None,
        str(tmp_path / "ws"),
        build_llm=lambda prov: llm,
        session_base=str(tmp_path / "sessions"),
    )

    async def drive():
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#prompt")
            await pilot.press(*"do it")
            await pilot.press("enter")
            await _wait_input_enabled(app, pilot)
            labels = all_labels(app.query_one(ActivityTree).root)
            text = "\n".join(labels)
            # brain states at the top level, the commissioned run nested inside
            assert "decide" in text and "do_run" in text
            assert "std_cot" in text and "solve" in text
            assert "4." in app.history

            # inspector: hidden by default, F2 shows it, content is filled
            panel = app.query_one(Inspector)
            assert panel.styles.visibility == "hidden"
            await pilot.press("f2")
            assert panel.styles.visibility == "visible"
            from textual.widgets import Static

            session_text = str(app.query_one("#inspector-session", Static).render())
            assert app.session.id in session_text

            # a second turn resets the tree to the new turn only
            await pilot.click("#prompt")
            await pilot.press(*"again")
            await pilot.press("enter")
            await _wait_input_enabled(app, pilot)
            labels2 = all_labels(app.query_one(ActivityTree).root)
            assert any("again" in label for label in labels2)
            assert not any("do it" in label for label in labels2)

    asyncio.run(drive())


def test_responsive_inspector_and_activity_toggle(tmp_path):
    from mklang.console.widgets import ActivityTree, Inspector

    app = build_app(
        CONFIG,
        None,
        str(tmp_path / "ws"),
        build_llm=lambda prov: scripted_llm({}, [4]),
        session_base=str(tmp_path / "sessions"),
    )

    async def drive():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f2")
            assert app.query_one("#body").has_class("inspector-narrow")
            assert app.query_one(Inspector).styles.visibility == "visible"
            await pilot.press("f2")
            assert app.query_one(Inspector).styles.visibility == "hidden"
            await pilot.press("ctrl+t")
            assert app.query_one(ActivityTree).has_class("hidden")

    asyncio.run(drive())


def test_slash_parser_supports_quoted_values():
    from mklang.console.commands import parse_command

    cmd, args = parse_command('/run demo task="hello world"')
    assert cmd == "/run"
    assert args == ["demo", "task=hello world"]


def test_slash_commands(tmp_path):
    llm = scripted_llm({}, [4])
    app = build_app(
        CONFIG,
        None,
        str(tmp_path / "ws"),
        build_llm=lambda prov: llm,
        session_base=str(tmp_path / "sessions"),
    )

    async def drive():
        async with app.run_test() as pilot:

            async def cmd(text):
                await pilot.click("#prompt")
                await pilot.press(*text)
                await pilot.press("enter")
                await pilot.pause(0.05)

            await cmd("/help")
            assert any("/machines" in line for line in app.log_history)
            await cmd("/machines")
            assert any("std_cot" in line for line in app.log_history)
            await cmd("/budget 500")
            assert app.tools.default_cost_budget == 500
            await cmd("/xyz")
            assert any("unknown command /xyz" in line for line in app.log_history)
            await cmd("/session")
            assert any(app.session.id in line for line in app.log_history)

            await cmd("/run std_cot task=hello")
            await _wait_input_enabled(app, pilot)
            assert any("result:" in line and '"status": "done"' in line for line in app.log_history)

    asyncio.run(drive())


def test_clarify_turn_uses_answer_mode(tmp_path):
    llm = scripted_llm(
        {
            "single next action": "CLARIFY: staging or prod?",
            "final reply": "Done on staging.",
        },
        [2, 4],
    )
    app = build_app(
        CONFIG,
        None,
        str(tmp_path / "ws"),
        build_llm=lambda prov: llm,
        session_base=str(tmp_path / "sessions"),
    )

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
