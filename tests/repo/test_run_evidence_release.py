"""Named evidence-release runner: estimate mode, catalog, OpenRouter Anthropic path."""

from __future__ import annotations

import json
import sys

import pytest
import yaml
from conftest import REPO_ROOT
from jsonschema import Draft7Validator

ROOT = REPO_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _runner():
    path = ROOT / "scripts" / "run_evidence_release.py"
    if not path.is_file():
        pytest.skip("scripts/run_evidence_release.py not present (sdist build)")
    from scripts import run_evidence_release

    return run_evidence_release


def test_estimate_prints_cited_table_and_makes_no_network(monkeypatch, capsys):
    runner = _runner()

    def boom(*_a, **_k):
        raise AssertionError("estimate mode must not load a provider or call a model")

    monkeypatch.setattr("mklang.config.load_provider", boom)
    monkeypatch.setattr("mklang.cli._build_llm", boom)
    code = runner.main(["--estimate"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Hard cap: $10.00" in out
    assert "gate-divergence" in out
    assert "gate-divergence-anthropic-openrouter" in out
    assert "repair-convergence" in out
    assert "first-true-live" in out
    assert "https://github.com/gianlucamazza/mklang/issues/60" in out
    assert "https://api-docs.deepseek.com/quick_start/pricing" in out
    assert "https://developers.openai.com/api/docs/models/gpt-5.6-luna" in out
    assert "https://openrouter.ai/anthropic/claude-sonnet-5" in out
    assert "anthropic/claude-sonnet-5" in out


def test_named_experiments_match_the_seven_machine_suite_and_corpus():
    runner = _runner()
    catalog = runner.named_experiments()
    gd = catalog["gate-divergence"]
    assert gd.run_count == 7 * 2 * 3
    assert set(gd.providers) == {"deepseek", "openai"}
    assert all(name in gd.argv[gd.argv.index("--machines") + 1] for name in runner.SEVEN_MACHINES)
    assert "hostile_" not in gd.argv[gd.argv.index("--machines") + 1]

    anth = catalog["gate-divergence-anthropic-openrouter"]
    assert anth.models["openrouter"] == "anthropic/claude-sonnet-5"
    assert anth.run_count == 7 * 3

    from scripts import repair_convergence as rc

    repair = catalog["repair-convergence"]
    assert repair.run_count == len(rc.CORPUS) * 3 * 3
    assert repair.providers == ("openai",)

    first = catalog["first-true-live"]
    assert first.run_count == 2
    assert "--live" in first.argv
    assert "priority_shadow" in first.argv

    for spec_exp in catalog.values():
        assert len(runner.planned_runs(spec_exp)) == spec_exp.run_count
        summary = runner.estimate_experiment(spec_exp)
        assert summary["usd_est"] > 0
        assert summary["usd_est"] < 10.0


def test_evidence_release_config_pins_openrouter_to_anthropic_and_validates():
    config_path = ROOT / "config" / "evidence-release.yaml"
    schema_path = ROOT / "config" / "runtime.schema.json"
    if not config_path.is_file():
        pytest.skip("config/evidence-release.yaml not present (sdist build)")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft7Validator(schema).validate(config)
    openrouter = config["providers"]["openrouter"]
    assert openrouter["api_key_env"] == "OPENROUTER_API_KEY"
    assert openrouter["tiers"]["fast"] == "anthropic/claude-sonnet-5"
    assert openrouter["tiers"]["balanced"] == "anthropic/claude-sonnet-5"
    assert openrouter["tiers"]["reasoning"] == "anthropic/claude-sonnet-5"
    assert config["providers"]["openai"]["tiers"]["balanced"] == "gpt-5.6-luna"


def test_evidence_live_workflow_is_dispatch_only():
    path = ROOT / ".github" / "workflows" / "evidence-live.yml"
    if not path.is_file():
        pytest.skip(".github/workflows not present (sdist build)")
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML 1.1 treats unquoted `on` as boolean true.
    triggers = workflow.get("on") or workflow.get(True)
    assert list(triggers.keys()) == ["workflow_dispatch"]
    options = triggers["workflow_dispatch"]["inputs"]["experiment"]["options"]
    assert "estimate" in options
    assert "gate-divergence" in options
    assert "gate-divergence-anthropic-openrouter" in options
    assert "repair-convergence" in options
    assert "first-true-live" in options
    text = path.read_text(encoding="utf-8")
    assert "schedule:" not in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert workflow["concurrency"]["group"] == "evidence-live"
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert workflow["permissions"]["contents"] == "read"
    assert workflow["permissions"]["actions"] == "read"
    assert "Require prior live runs in the checked-out ledger" in text
    assert "--require-prior-live-runs" in text
    # The prior-run check is a separate step so a failed check does not
    # count as "reached the live step".
    require_at = text.index("Require prior live runs in the checked-out ledger")
    live_at = text.index("Live named experiment")
    assert require_at < live_at


def test_harnesses_guard_before_each_model_run():
    """Cap check is inside each provider/repeat/arm loop, not once per experiment."""
    gd = ROOT / "scripts" / "gate_divergence.py"
    rc = ROOT / "scripts" / "repair_convergence.py"
    ft = ROOT / "scripts" / "first_true_eval.py"
    if not gd.is_file():
        pytest.skip("harness scripts not present (sdist build)")
    gd_loop = gd.read_text(encoding="utf-8").split("for i in range(args.repeats)", 1)[1]
    assert gd_loop.index("maybe_guard(") < gd_loop.index("row = _run_once(")
    rc_loop = rc.read_text(encoding="utf-8").split("for arm in arms:", 1)[1]
    assert rc_loop.index("maybe_guard(") < rc_loop.index("row = _run_once(")
    ft_loop = ft.read_text(encoding="utf-8").split("for i in range(args.repeats)", 1)[1]
    assert ft_loop.index("maybe_guard(") < ft_loop.index("run_live_trial(")
    assert "pending_usd=pending" in ft_loop


def test_require_prior_live_runs_fails_closed_without_actions_env(monkeypatch, capsys):
    runner = _runner()
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    code = runner.main(["--require-prior-live-runs"])
    assert code == 3
    assert "GITHUB_REPOSITORY" in capsys.readouterr().err


def test_quality_job_names_are_unchanged():
    path = ROOT / ".github" / "workflows" / "quality.yml"
    if not path.is_file():
        pytest.skip(".github/workflows not present (sdist build)")
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "checks" in workflow["jobs"]
    assert "test" in workflow["jobs"]
