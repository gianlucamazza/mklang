"""The bundled `std_*` machine stdlib: validity, scenarios, registry precedence."""

from pathlib import Path

import pytest
import yaml

from mklang import host
from mklang.engine import run
from mklang.lint import lint_machine
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.loader import semantic_check, validate_dict
from mklang.registry import base_registry, load_stdlib_registry
from mklang.scripttest import match_expectation, run_scenario

CONFIG = "config/runtime.example.yaml"
STDLIB_DIR = Path(__file__).resolve().parents[1] / "src" / "mklang" / "data" / "stdlib"
STDLIB_FILES = sorted(STDLIB_DIR.glob("*.mk"))
EXPECTED = {
    "std_cascade",
    "std_compress",
    "std_cot",
    "std_debate",
    "std_map_reduce",
    "std_plan_execute",
    "std_refine",
    "std_research",
    "std_self_consistency",
    "std_tot",
}


def build_llm(prov):
    return MockLLM(produce_fn=lambda model, system, user, reason: Produced(text=user))


def test_stdlib_lineup_and_registry_load():
    assert {f.stem for f in STDLIB_FILES} == EXPECTED
    reg = load_stdlib_registry()
    assert set(reg) == EXPECTED
    for name, m in reg.items():
        assert m.name == name  # filename = machine name convention


@pytest.mark.parametrize("path", STDLIB_FILES, ids=lambda p: p.stem)
def test_stdlib_machine_is_clean(path):
    """Schema-valid, zero semantic errors AND warnings, zero lint findings."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate_dict(doc)
    reg = load_stdlib_registry()
    errors, warnings = semantic_check(reg[path.stem], reg, strict=True)
    assert errors == [] and warnings == []
    assert lint_machine(reg[path.stem]) == []


@pytest.mark.parametrize("path", STDLIB_FILES, ids=lambda p: p.stem)
def test_stdlib_scenarios_pass(path):
    """Every bundled .test.yaml scenario passes under the scripted harness."""
    script = path.with_suffix(".test.yaml")
    assert script.is_file(), f"{path.stem} ships without scenario tests"
    scenarios = yaml.safe_load(script.read_text(encoding="utf-8"))["scenarios"]
    assert len(scenarios) >= 2
    machine = load_stdlib_registry()[path.stem]
    for sc in scenarios:
        result = run_scenario(machine, load_stdlib_registry(), sc)
        mismatches = match_expectation(result, sc["expect"])
        assert not mismatches, f"{path.stem}::{sc['name']}: {mismatches[0]}"


def test_inline_source_can_call_stdlib():
    caller = (
        "machine: wrapper\nentry: w\nbudget: 4\nresult: out\n"
        "states:\n  w:\n    call: std_cot\n    input: {task: 'say hi'}\n"
        "    output: out\n    gates: [{when: otherwise, then: ok, to: END}]\n"
    )
    p = host.prepare_source(CONFIG, None, caller, build_llm=build_llm)
    res = run(p.machine, dict(p.machine.context), p.registry, p.llm, p.prov.tiers)
    assert res.status == "done"
    assert "say hi" in str(res.result)  # std_cot's prompt echoed by the mock


def test_run_by_name_resolves_stdlib():
    p = host.prepare_path(CONFIG, None, "std_cot", build_llm=build_llm)
    assert p.machine.name == "std_cot"
    res = run(p.machine, {**p.machine.context, "task": "2+2?"}, p.registry, p.llm, p.prov.tiers)
    assert res.status == "done"


def test_run_by_unknown_name_still_errors():
    with pytest.raises(host.PrepareError) as ei:
        host.prepare_path(CONFIG, None, "std_nonexistent", build_llm=build_llm)
    assert ei.value.kind == "load"


def test_user_machine_shadows_stdlib_with_warning(tmp_path):
    shadow = (
        "machine: std_cot\nentry: s\nbudget: 3\nresult: answer\n"
        "states:\n  s:\n    structure: s\n    prompt: 'my own cot'\n    output: answer\n"
        "    gates: [{when: otherwise, then: ok, to: END}]\n"
    )
    f = tmp_path / "std_cot.mk"
    f.write_text(shadow, encoding="utf-8")
    p = host.prepare_path(CONFIG, None, str(f), build_llm=build_llm)
    assert p.registry["std_cot"] is p.machine  # the user machine wins
    assert any("shadows the bundled stdlib machine" in w for w in p.warnings)


def test_run_by_name_checkpoint_roundtrip(tmp_path, monkeypatch, capsys):
    """CLI run-by-name + --checkpoint: sha is None (no file to pin), resume works."""
    import json

    from mklang import cli

    def hitl_llm():
        # judge 1 is out of range for draft's 1-condition batch → fallback to
        # otherwise → escalate → suspends under --hitl
        return MockLLM(
            produce_fn=lambda model, system, user, reason: Produced(text=user),
            judge_fn=lambda *a: 1,
        )

    monkeypatch.setattr(cli, "_build_llm", lambda prov: hitl_llm())
    ck = str(tmp_path / "ck.json")
    rc = cli.main(["run", "std_cascade", "--set", "task=hard one", "--checkpoint", ck, "--hitl"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 3 and out["status"] == "suspended"
    assert json.loads(Path(ck).read_text())["machine_sha256"] is None

    monkeypatch.setattr(cli, "_build_llm", lambda prov: build_llm(None))
    rc = cli.main(["resume", ck])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["status"] == "done"


def test_cli_machines_lists_stdlib(capsys, tmp_path, monkeypatch):
    import json

    from mklang import cli

    # Isolate from the host: a real user machines dir must not leak in.
    monkeypatch.setenv("MKLANG_DATA_DIR", str(tmp_path / "data"))
    assert cli.main(["machines"]) == 0
    out = json.loads(capsys.readouterr().out)
    names = {m["name"]: m for m in out}
    assert set(names) == EXPECTED
    assert names["std_cot"]["source"] == "stdlib"
    assert names["std_refine"]["context"]["criteria"] == "clear, correct, and complete"

    (tmp_path / "mine.mk").write_text(
        "machine: mine\nentry: s\nbudget: 3\nstates:\n  s:\n    structure: s\n"
        "    prompt: p\n    output: o\n    gates: [{when: otherwise, then: ok, to: END}]\n",
        encoding="utf-8",
    )
    assert cli.main(["machines", "--dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    local = {m["name"]: m["source"] for m in out}
    assert local["mine"] == "local"


def test_base_registry_is_a_fresh_copy():
    r1, r2 = base_registry(), base_registry()
    assert r1 is not r2
    r1["x"] = None
    assert "x" not in base_registry()
