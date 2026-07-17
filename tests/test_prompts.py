"""Produce system prompt assembly (structure + execution → system channel)."""

from mklang.llm.prompts import build_produce_system
from mklang.model import State


def _gen(**kwargs) -> State:
    base = dict(
        id="s",
        kind="generative",
        gates=[],
        output="o",
        structure="a short answer",
        prompt="task {{q}}",
    )
    base.update(kwargs)
    return State(**base)


def test_build_produce_system_sections_and_structure():
    sys_msg = build_produce_system(_gen(structure="JSON array of strings only"))
    assert "## Output contract (structure)" in sys_msg
    assert "JSON array of strings only" in sys_msg
    assert "## Operational policy (execution)" in sys_msg
    assert "No additional operational policy." in sys_msg
    assert "## Rules" in sys_msg
    assert "Emit only the content required" in sys_msg


def test_build_produce_system_includes_execution_policy():
    sys_msg = build_produce_system(
        _gen(execution="Never invent web results. Ground only in tool notes.")
    )
    assert "Never invent web results" in sys_msg
    assert "No additional operational policy." not in sys_msg


def test_build_produce_system_does_not_interpolate_braces():
    """structure is not render()'d — {{paths}} stay literal (must live in prompt)."""
    sys_msg = build_produce_system(_gen(structure="Uses {{today}} wrongly"))
    assert "{{today}}" in sys_msg


def test_engine_system_delegates_to_builder():
    from mklang.engine import _system

    s = _gen(structure="shape-x", execution="policy-y")
    text = _system(s)
    assert "shape-x" in text and "policy-y" in text
    assert "Output contract" in text
