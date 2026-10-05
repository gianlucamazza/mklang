"""Offline tests for scripts/first_true_eval.py — no keys, no network."""

from __future__ import annotations

import importlib.util
import json

import pytest
from conftest import REPO_ROOT
from jsonschema import Draft7Validator

from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM

ROOT = REPO_ROOT
FIXTURE = ROOT / "scripts" / "fixtures" / "first_true_eval.json"


def _module():
    path = ROOT / "scripts" / "first_true_eval.py"
    if not path.is_file():
        pytest.skip("scripts/first_true_eval.py not present (sdist build)")
    spec = importlib.util.spec_from_file_location("first_true_eval", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fte = _module()


def _validator() -> Draft7Validator:
    schema = json.loads(
        (ROOT / "schema" / "experiment-result.schema.json").read_text(encoding="utf-8")
    )
    return Draft7Validator(schema)


def test_fixture_is_content_hashable_and_stable():
    first = fte.fixture_hash(FIXTURE)
    second = fte.fixture_hash(FIXTURE)
    assert first == second
    assert len(first) == 64


def test_fixture_cases_match_gate_divergence_gold():
    fixture = fte.load_fixture(FIXTURE)
    names = {c["name"] for c in fixture["cases"]}
    for required in ("gate_divergence", "priority_shadow", "none_holds", "threshold_edge"):
        assert required in names
    for case in fixture["cases"]:
        assert fte.validate_case(case) == []
        assert case["name"] in fte.MACHINES
        assert case["gold_to"] == fte.GOLD[case["name"]].split(" || ", 1)[0].split(">", 1)[1]


def test_priority_shadow_holds_both_conditions():
    fixture = fte.load_fixture(FIXTURE)
    case = next(c for c in fixture["cases"] if c["name"] == "priority_shadow")
    assert case["holds"] == [True, True]
    assert case["produce"] == "REFUND 2000 EUR APPROVED FOR ORDER 71"
    assert case["gold_to"] == "broad"


def test_mock_first_true_honours_document_order():
    gates = fte.entry_gates("priority_shadow")
    pred, fail = fte.first_true_pick(gates, [True, True])
    assert pred == "broad"
    assert fail is None


def test_mock_spaghetti_picks_later_narrower_match():
    gates = fte.entry_gates("priority_shadow")
    pred, fail = fte.spaghetti_pick(gates, [True, True])
    assert pred == "narrow"
    assert fail is None


@pytest.mark.parametrize(
    "name,gold",
    [
        ("gate_divergence", "spam_path"),
        ("priority_shadow", "broad"),
        ("none_holds", "other"),
        ("threshold_edge", "within"),
        ("severity_escalate", "auto"),
    ],
)
def test_mock_first_true_matches_gold_on_every_fixture_machine(name, gold):
    fixture = fte.load_fixture(FIXTURE)
    case = next(c for c in fixture["cases"] if c["name"] == name)
    gates = fte.entry_gates(name)
    pred, fail = fte.first_true_pick(gates, case["holds"])
    assert pred == gold
    assert fail is None


def test_mock_trial_pairs_both_arms_on_the_same_produce():
    fixture = fte.load_fixture(FIXTURE)
    case = next(c for c in fixture["cases"] if c["name"] == "priority_shadow")
    rows = fte.run_mock_trial(case, fixture_sha=fte.fixture_hash(FIXTURE))
    assert [r["arm"] for r in rows] == ["first_true", "prompt_spaghetti"]
    assert {r["produce_hash"] for r in rows} == {fte.produce_hash(case["produce"])}
    assert rows[0]["pred_to"] == "broad" and rows[0]["correct"] is True
    assert rows[1]["pred_to"] == "narrow" and rows[1]["correct"] is False
    assert rows[1]["fail_mode"] == "wrong_to"


def test_summary_reports_priority_shadow_fidelity():
    fixture = fte.load_fixture(FIXTURE)
    sha = fte.fixture_hash(FIXTURE)
    rows: list[dict] = []
    for case in fixture["cases"]:
        rows.extend(fte.run_mock_trial(case, fixture_sha=sha))
    summary = fte.summarize(
        rows,
        fixture_sha=sha,
        fixture_path="scripts/fixtures/first_true_eval.json",
        mode="mock",
        machines=[c["name"] for c in fixture["cases"]],
    )
    shadow = summary["priority_shadow_fidelity"]
    assert shadow["n"] == 1
    assert shadow["acc_first_true"] == 1.0
    assert shadow["acc_spaghetti"] == 0.0
    assert shadow["first_true_wins"] == 1.0
    assert summary["per_machine"]["priority_shadow"]["acc_A"] == 1.0
    assert summary["per_machine"]["priority_shadow"]["acc_B"] == 0.0
    assert "latency_ms" not in str(summary["note"])
    assert "€" not in json.dumps(summary)
    table = fte.render_table(summary)
    assert "priority_shadow" in table
    assert "acc_A" in table


def test_self_check_cli_is_green_and_writes_artifacts(tmp_path, capsys):
    jsonl = tmp_path / "rows.jsonl"
    summary_path = tmp_path / "summary.json"
    assert (
        fte.main(
            [
                "--self-check",
                "--jsonl",
                str(jsonl),
                "--summary-json",
                str(summary_path),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["mode"] == "mock"
    assert summary["experiment"] == "first-true-fidelity"
    assert len(summary["fixture_hash"]) == 64
    assert summary["priority_shadow_fidelity"]["first_true_wins"] == 1.0
    assert "first-true gate routing" in summary["methods"]
    assert "€" not in captured.out
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    validator = _validator()
    for line in lines:
        row = json.loads(line)
        assert list(validator.iter_errors(row)) == []
        assert row["mode"] == "mock"
        assert "latency_ms" not in (row.get("metrics") or {})


def test_paraphrase_variants_are_labeled_separately():
    fixture = fte.load_fixture(FIXTURE)
    cases = fte.expand_cases(fixture, machines=["priority_shadow"], paraphrase=True)
    variants = {c["variant"] for c in cases}
    assert variants == {"base", "p1"}
    for case in cases:
        assert fte.validate_case(case) == []
        gates = fte.entry_gates(case["name"], case["variant"])
        assert fte.first_true_pick(gates, case["holds"])[0] == "broad"


def test_live_path_skips_when_provider_has_no_key(monkeypatch):
    class Prov:
        def __init__(self) -> None:
            self.name = "deepseek"
            self.api_key = ""
            self.tiers = {"fast": "fixture"}
            self.params: dict = {}

        def judge_override(self) -> None:
            return None

    monkeypatch.setattr(fte, "load_provider", lambda *_a, **_k: Prov())
    fixture = fte.load_fixture(FIXTURE)
    case = next(c for c in fixture["cases"] if c["name"] == "priority_shadow")
    rows = fte.run_live_trial(
        case,
        provider_name="deepseek",
        config=fte.DEFAULT_CONFIG,
        fixture_sha=fte.fixture_hash(FIXTURE),
        repeat=0,
    )
    assert {r["status"] for r in rows} == {"skipped"}
    assert all(r["reason"] == "no API key" for r in rows)


def test_injected_live_judge_still_pairs_arms_on_pinned_produce():
    """Live path with a scripted LLM: first-true vs unordered pick, no network."""

    def build(_prov):
        def judge_fn(model, conditions, output, context, reasoning=None):
            # Honour first-true: both refund conditions hold; return the first.
            return 0

        def produce_fn(model, system, user, reason):
            # Spaghetti: pick the refund-above-1000 option wherever it was shown.
            lines = [
                line
                for line in user.splitlines()
                if "refund above 1000" in line or "refund larger than 1000" in line
            ]
            number = int(lines[0].split(".", 1)[0]) if lines else 2
            return Produced(text=json.dumps({"choice": number}), input_tokens=3, output_tokens=1)

        return MockLLM(produce_fn=produce_fn, judge_fn=judge_fn)

    fixture = fte.load_fixture(FIXTURE)
    case = next(c for c in fixture["cases"] if c["name"] == "priority_shadow")
    rows = fte.run_live_trial(
        case,
        provider_name="deepseek",
        config=fte.DEFAULT_CONFIG,
        fixture_sha=fte.fixture_hash(FIXTURE),
        repeat=0,
        build_llm=build,
    )
    by_arm = {r["arm"]: r for r in rows}
    assert by_arm["first_true"]["pred_to"] == "broad"
    assert by_arm["prompt_spaghetti"]["pred_to"] == "narrow"
    assert by_arm["first_true"]["mode"] == "live"
    assert "latency_ms" in by_arm["first_true"]["metrics"]
    assert by_arm["prompt_spaghetti"]["usage"]["output_tokens"] == 1


def test_unknown_machine_is_a_cli_error(capsys):
    with pytest.raises(SystemExit):
        fte.main(["--machines", "not_a_machine"])


def test_methods_paragraph_names_the_reproducible_command():
    assert "scripts/gate_divergence.py" in fte.METHODS_PARAGRAPH
    assert "priority_shadow" in fte.METHODS_PARAGRAPH
    readme = (ROOT / "docs" / "experiments" / "first-true-fidelity.md").read_text(encoding="utf-8")
    assert "uv run python scripts/first_true_eval.py" in readme
    assert "tip SHA" in readme or "tip_sha" in readme
