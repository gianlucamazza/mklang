"""Offline helpers for scripts/jev_noul_eval.py — no keys, no network."""

from __future__ import annotations

import importlib.util

from conftest import REPO_ROOT

from mklang.model import parse_machine


def _module():
    spec = importlib.util.spec_from_file_location(
        "jev_noul_eval", REPO_ROOT / "scripts" / "jev_noul_eval.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _module()


def test_pinned_outputs_cover_gold_machines():
    assert set(ev.PINNED_OUTPUT) == set(ev.GOLD_FIRST)
    for name in ev.CORE_MACHINES:
        parse_machine(ev.MACHINES[name])


def test_priority_shadow_gold_is_broad_not_narrow():
    doc = ev.MACHINES["priority_shadow"]
    conds = ev.entry_prose_conditions("priority_shadow", doc)
    assert conds[0] == "the reply mentions a refund"
    assert ev.gold_first_target("priority_shadow", doc, 0, len(conds)) == "broad"
    assert ev.gold_first_target("priority_shadow", doc, 1, len(conds)) == "narrow"
    assert ev.gold_first_target("priority_shadow", doc, len(conds), len(conds)) == "neither"
    assert ev.GOLD_FIRST["priority_shadow"] == "broad"


def test_none_holds_gold_is_otherwise():
    doc = ev.MACHINES["none_holds"]
    conds = ev.entry_prose_conditions("none_holds", doc)
    assert ev.gold_first_target("none_holds", doc, len(conds), len(conds)) == "other"


def test_path_b_stops_on_priority_shadow_miss():
    verdict = ev.path_b_verdict(
        {"priority_shadow_acc": 0.0, "injection_acc": 1.0, "fence_applied": True}
    )
    assert verdict["verdict"] == "STOP"
    assert verdict["production_ready"] is False
    assert verdict["choice_mapping"] == "STOP"
    assert any("priority_shadow" in s for s in verdict["stops"])


def test_path_b_stops_on_injection_miss():
    verdict = ev.path_b_verdict(
        {"priority_shadow_acc": 1.0, "injection_acc": 0.833, "fence_applied": True}
    )
    assert verdict["verdict"] == "STOP"
    assert "0.833" in verdict["stops"][0]


def test_path_b_hold_is_not_production_ready():
    verdict = ev.path_b_verdict(
        {"priority_shadow_acc": 1.0, "injection_acc": 1.0, "fence_applied": True}
    )
    assert verdict["verdict"] == "HOLD"
    assert verdict["production_ready"] is False


def test_skip_report_does_not_invent_results():
    report = ev._skip_report()
    assert report["skipped"] is True
    assert report["invented_results"] is False
    assert "TYPESAFE_API_KEY" in report["reason"]
    assert "jev_noul_eval.py" in report["how_to_run"]
