"""Cost ledger + $10 cap guard. No provider calls."""

from __future__ import annotations

import json
import sys

import pytest
from conftest import REPO_ROOT

ROOT = REPO_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ledger():
    path = ROOT / "scripts" / "cost_ledger.py"
    if not path.is_file():
        pytest.skip("scripts/cost_ledger.py not present (sdist build)")
    from scripts import cost_ledger

    return cost_ledger


def test_every_price_has_source_and_retrieval_date():
    cl = _ledger()
    assert cl.USD_CAP == 10.0
    assert cl.LEDGER_NAME == "costs.jsonl"
    for (provider, model), price in cl.PRICES.items():
        assert price.source.startswith("https://"), (provider, model)
        assert price.retrieved == "2026-10-10"
        assert price.input_usd_per_mtok > 0
        assert price.output_usd_per_mtok > 0


def test_token_estimates_are_cited():
    cl = _ledger()
    gd = cl.TOKEN_ESTIMATES["gate-divergence"]
    assert gd.tokens == 30_000 // 12
    assert "issues/60" in gd.source
    repair = cl.TOKEN_ESTIMATES["repair-convergence"]
    assert repair.tokens == 40_000
    assert "cost_budget" in repair.source


def test_empty_ledger_allows_a_run_under_the_cap(tmp_path):
    cl = _ledger()
    ledger = tmp_path / "costs.jsonl"
    estimate = cl.refuse_if_over_cap(
        ledger,
        provider="deepseek",
        model="deepseek-v4-flash",
        experiment="gate-divergence",
        cap=10.0,
    )
    assert estimate > 0
    assert estimate < 10.0


def test_guard_refuses_when_ledger_plus_estimate_exceeds_cap(tmp_path):
    cl = _ledger()
    ledger = tmp_path / "costs.jsonl"
    estimate, _ = cl.estimate_run_usd("openai", "gpt-5.6-luna", "gate-divergence")
    cl.append_cost_row(
        ledger,
        provider="openai",
        model="gpt-5.6-luna",
        input_tokens=0,
        output_tokens=0,
        run_id="seed",
        experiment="gate-divergence",
        usd=10.0 - (estimate / 2),
        usd_source="fixture",
    )
    with pytest.raises(cl.CapExceededError, match="exceeds cap"):
        cl.refuse_if_over_cap(
            ledger,
            provider="openai",
            model="gpt-5.6-luna",
            experiment="gate-divergence",
            cap=10.0,
        )


def test_pending_estimate_counts_toward_the_cap(tmp_path):
    cl = _ledger()
    ledger = tmp_path / "costs.jsonl"
    estimate, _ = cl.estimate_run_usd("deepseek", "deepseek-v4-flash", "first-true-fidelity")
    cl.append_cost_row(
        ledger,
        provider="deepseek",
        model="deepseek-v4-flash",
        input_tokens=0,
        output_tokens=0,
        run_id="seed",
        experiment="first-true-fidelity",
        usd=10.0 - estimate - 0.0000001,
        usd_source="fixture",
    )
    cl.refuse_if_over_cap(
        ledger,
        provider="deepseek",
        model="deepseek-v4-flash",
        experiment="first-true-fidelity",
        cap=10.0,
    )
    with pytest.raises(cl.CapExceededError):
        cl.refuse_if_over_cap(
            ledger,
            provider="deepseek",
            model="deepseek-v4-flash",
            experiment="first-true-fidelity",
            cap=10.0,
            pending_usd=estimate,
        )


def test_append_uses_pinned_price_and_increments_total(tmp_path):
    cl = _ledger()
    ledger = tmp_path / "costs.jsonl"
    price = cl.lookup_price("openrouter", "anthropic/claude-sonnet-5")
    row = cl.append_cost_row(
        ledger,
        provider="openrouter",
        model="anthropic/claude-sonnet-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        run_id="gate-divergence/openrouter/x/0",
        experiment="gate-divergence",
        timestamp="2026-10-10T00:00:00Z",
    )
    assert row["usd"] == pytest.approx(price.input_usd_per_mtok + price.output_usd_per_mtok)
    assert row["usd_source"] == "price-table"
    assert row["price_source"] == price.source
    assert row["price_retrieved"] == "2026-10-10"
    assert cl.ledger_total_usd(ledger) == pytest.approx(row["usd"])
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["provider"] == "openrouter"
    assert parsed["model"] == "anthropic/claude-sonnet-5"


def test_actual_over_estimate_is_appended_and_blocks_the_next_run(tmp_path):
    """The guard is per model run. A high actual is counted before the next start."""
    cl = _ledger()
    ledger = tmp_path / "costs.jsonl"
    estimate, _ = cl.estimate_run_usd("openai", "gpt-5.6-luna", "gate-divergence")
    first = cl.refuse_if_over_cap(
        ledger,
        provider="openai",
        model="gpt-5.6-luna",
        experiment="gate-divergence",
        cap=10.0,
    )
    assert first == pytest.approx(estimate)
    cl.append_cost_row(
        ledger,
        provider="openai",
        model="gpt-5.6-luna",
        input_tokens=0,
        output_tokens=0,
        run_id="actual-high",
        experiment="gate-divergence",
        usd=10.0 - estimate + 0.001,
        usd_source="price-table",
        github_run_id="111",
    )
    assert cl.ledger_total_usd(ledger) == pytest.approx(10.0 - estimate + 0.001)
    with pytest.raises(cl.CapExceededError, match="exceeds cap"):
        cl.refuse_if_over_cap(
            ledger,
            provider="openai",
            model="gpt-5.6-luna",
            experiment="gate-divergence",
            cap=10.0,
        )


def _prior_fixture():
    path = ROOT / "tests" / "repo" / "fixtures" / "evidence_live_workflow_runs.json"
    if not path.is_file():
        pytest.skip("prior-run fixture not present (sdist build)")
    return json.loads(path.read_text(encoding="utf-8"))


def test_prior_live_run_ids_from_fixture_listings():
    cl = _ledger()
    fixture = _prior_fixture()
    required = cl.prior_live_run_ids_from_listings(
        fixture["workflow_runs"],
        fixture["jobs_by_run_id"],
        current_run_id=fixture["current_run_id"],
    )
    assert required == fixture["required_prior_ids"]
    assert "555" not in required
    assert "333" not in required
    assert "444" not in required


def test_missing_prior_live_run_ids_fail_closed_until_ledger_has_them(tmp_path):
    cl = _ledger()
    fixture = _prior_fixture()
    required = fixture["required_prior_ids"]
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert cl.missing_prior_live_run_ids(required, cl.parse_ledger(empty)) == required

    partial = tmp_path / "partial.jsonl"
    cl.append_cost_row(
        partial,
        provider="deepseek",
        model="deepseek-v4-flash",
        input_tokens=0,
        output_tokens=0,
        run_id="from-111",
        experiment="gate-divergence",
        usd=0.0,
        usd_source="dispatch-open",
        github_run_id="111",
    )
    assert cl.missing_prior_live_run_ids(required, cl.parse_ledger(partial)) == ["222", "666"]

    complete = tmp_path / "complete.jsonl"
    for rid in required:
        cl.append_dispatch_marker(complete, github_run_id=rid, experiment="gate-divergence")
    assert cl.missing_prior_live_run_ids(required, cl.parse_ledger(complete)) == []
    cl.require_prior_live_runs_in_ledger(
        complete,
        current_run_id=fixture["current_run_id"],
        workflow_runs=fixture["workflow_runs"],
        jobs_by_run_id=fixture["jobs_by_run_id"],
    )


def test_require_prior_live_runs_raises_when_unmerged(tmp_path):
    cl = _ledger()
    fixture = _prior_fixture()
    ledger = tmp_path / "costs.jsonl"
    ledger.write_text("", encoding="utf-8")
    with pytest.raises(cl.UnmergedLedgerError, match="111, 222, 666"):
        cl.require_prior_live_runs_in_ledger(
            ledger,
            current_run_id=fixture["current_run_id"],
            workflow_runs=fixture["workflow_runs"],
            jobs_by_run_id=fixture["jobs_by_run_id"],
        )


def test_unknown_model_has_no_invented_price():
    cl = _ledger()
    with pytest.raises(cl.UnknownPriceError, match="no pinned list price"):
        cl.lookup_price("anthropic", "claude-sonnet-5")


def test_repair_self_check_stops_before_a_run_when_cap_is_already_spent(tmp_path, capsys):
    cl = _ledger()
    rc_path = ROOT / "scripts" / "repair_convergence.py"
    if not rc_path.is_file():
        pytest.skip("scripts/repair_convergence.py not present (sdist build)")
    from scripts import repair_convergence as rc

    ledger = tmp_path / "costs.jsonl"
    cl.append_cost_row(
        ledger,
        provider="openai",
        model="gpt-5.6-luna",
        input_tokens=0,
        output_tokens=0,
        run_id="seed",
        experiment="repair-convergence",
        usd=10.0,
        usd_source="fixture",
    )
    code = rc.main(
        [
            "--self-check",
            "--repeats",
            "1",
            "--cost-ledger",
            str(ledger),
            "--usd-cap",
            "10",
            "--config",
            str(ROOT / "config" / "evidence-release.yaml"),
            "--provider",
            "openai",
        ]
    )
    assert code == 3
    err = capsys.readouterr().err
    assert "cost cap" in err
    assert cl.ledger_total_usd(ledger) == pytest.approx(10.0)
