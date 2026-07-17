"""The console brain (agent.mk, ADR 0015 M1c): validity + scripted scenarios in CI."""

from pathlib import Path

import yaml

from mklang.lint import lint_machine
from mklang.loader import semantic_check, validate_dict
from mklang.model import parse_machine
from mklang.scripttest import match_expectation, run_scenario

AGENT_DIR = Path(__file__).resolve().parents[1] / "src" / "mklang" / "data" / "console"


def load_agent():
    doc = yaml.safe_load((AGENT_DIR / "agent.mk").read_text(encoding="utf-8"))
    validate_dict(doc)
    return parse_machine(doc)


def test_agent_machine_is_clean():
    m = load_agent()
    errors, warnings = semantic_check(m, {m.name: m}, strict=True)
    assert errors == [] and warnings == []
    assert lint_machine(m) == []
    assert m.result == "reply"
    assert {t for t in ("list_machines", "run_machine", "ask_user")} <= {
        s.tool for s in m.states.values() if s.kind == "tool"
    }


def test_agent_scenarios_pass():
    m = load_agent()
    doc = yaml.safe_load((AGENT_DIR / "agent.test.yaml").read_text(encoding="utf-8"))
    scenarios = doc["scenarios"]
    assert len(scenarios) >= 4  # direct, run, clarify, discover
    for sc in scenarios:
        result = run_scenario(m, {m.name: m}, sc)
        mismatches = match_expectation(result, sc["expect"])
        assert not mismatches, f"{sc['name']}: {mismatches[0]}"
