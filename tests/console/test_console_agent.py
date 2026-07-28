"""The console brain (agent.mkl, ADR 0015 M1c): validity + scripted scenarios in CI."""

import yaml
from conftest import REPO_ROOT

from mklang.console.workspace import requires_workspace_inspection
from mklang.hooks import console_workspace_ready
from mklang.lint import lint_machine
from mklang.loader import semantic_check, validate_dict
from mklang.model import parse_machine
from mklang.scripttest import match_expectation, run_scenario

AGENT_DIR = REPO_ROOT / "src" / "mklang" / "data" / "console"


def load_agent():
    doc = yaml.safe_load((AGENT_DIR / "agent.mkl").read_text(encoding="utf-8"))
    validate_dict(doc)
    return parse_machine(doc)


def test_agent_machine_is_clean():
    m = load_agent()
    errors, warnings = semantic_check(m, {m.name: m}, strict=True)
    assert errors == [] and warnings == []
    # Structural findings must be empty. The control-flow-taint notes are not
    # structural and are expected here: the brain routes to write_machine /
    # run_machine / update_task on prose gates over what the user typed, which is
    # external by definition (SPEC §6). The mitigation lives in the host — the
    # console asks for confirmation before an overwrite and before granting tool
    # capabilities to a run — not in the machine, so the note stays visible
    # instead of being suppressed.
    assert [f for f in lint_machine(m) if not f.startswith("note:")] == []
    assert sorted(f.split(":")[1].strip() for f in lint_machine(m) if "effectful tool" in f) == [
        "do_run",
        "save",
        "task_update",
    ]
    assert m.result == "reply"
    assert "workspace_root" in m.context
    assert {
        "list_machines",
        "run_machine",
        "ask_user",
        "list_workspace",
        "read_workspace_file",
        "search_workspace",
        "update_task",
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
