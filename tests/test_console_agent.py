"""The console brain (agent.mkl, ADR 0015 M1c): validity + scripted scenarios in CI."""

from pathlib import Path

import yaml

from mklang.lint import lint_machine
from mklang.loader import semantic_check, validate_dict
from mklang.model import parse_machine
from mklang.scripttest import match_expectation, run_scenario
from mklang.hooks import console_workspace_ready
from mklang.console.workspace import requires_workspace_inspection

AGENT_DIR = Path(__file__).resolve().parents[1] / "src" / "mklang" / "data" / "console"


def load_agent():
    doc = yaml.safe_load((AGENT_DIR / "agent.mkl").read_text(encoding="utf-8"))
    validate_dict(doc)
    return parse_machine(doc)


def test_agent_machine_is_clean():
    m = load_agent()
    errors, warnings = semantic_check(m, {m.name: m}, strict=True)
    assert errors == [] and warnings == []
    assert lint_machine(m) == []
    assert m.result == "reply"
    assert "workspace_root" in m.context
    assert {
        "list_machines",
        "run_machine",
        "ask_user",
        "list_workspace",
        "read_workspace_file",
        "search_workspace",
    } <= {s.tool for s in m.states.values() if s.kind == "tool"}


def test_agent_scenarios_pass():
    m = load_agent()
    doc = yaml.safe_load((AGENT_DIR / "agent.test.yaml").read_text(encoding="utf-8"))
    scenarios = doc["scenarios"]
    assert len(scenarios) >= 4  # direct, run, clarify, discover
    for sc in scenarios:
        result = run_scenario(m, {m.name: m}, sc)
        mismatches = match_expectation(result, sc["expect"])
        assert not mismatches, f"{sc['name']}: {mismatches[0]}"


def test_workspace_intent_and_readiness_guard():
    assert requires_workspace_inspection("analizza l'architettura del progetto") is True
    assert requires_workspace_inspection("quanto fa 2 + 2?") is False
    assert console_workspace_ready({"workspace_required": True}, None) is False
    assert (
        console_workspace_ready(
            {
                "workspace_required": True,
                "workspace_brief": "FACTS: README.md",
                "observation": ['{"tool": "read_workspace_file", "path": "README.md"}'],
            },
            None,
        )
        is True
    )
