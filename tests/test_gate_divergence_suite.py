"""Offline harness tests for scripts/gate_divergence.py — no keys, no network.

The release-gate helpers (`_ci_errors`, `_summary`) are also unit-tested in
test_release.py; here we cover the machine SUITE, the per-machine aggregation,
and that the harness actually drives a run end to end with a scripted LLM.
"""

import importlib.util
from pathlib import Path

import pytest

from mklang.llm.mock import MockLLM
from mklang.llm.base import Produced
from mklang.loader import semantic_check
from mklang.model import parse_machine

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "gate_divergence", ROOT / "scripts" / "gate_divergence.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gd = _module()


@pytest.mark.parametrize("name", list(gd.MACHINES))
def test_every_suite_machine_is_valid(name):
    m = parse_machine(gd.MACHINES[name])
    errors, _ = semantic_check(m, {m.name: m})
    assert errors == []
    assert m.name == name


def test_backcompat_machine_alias_points_at_gate_divergence():
    assert gd.MACHINE is gd.MACHINES["gate_divergence"]


# --- per-machine aggregation (rows fabricated; no run needed) --------------


def _row(provider, machine, signature, status="done"):
    return {
        "provider": provider,
        "machine": machine,
        "skipped": False,
        "status": status,
        "signature": signature,
        "output_hash": signature,
        "repeat": 0,
    }


def test_agreement_is_computed_within_each_machine():
    rows = [
        # machine A: the two providers agree
        _row("deepseek", "A", "sigA"),
        _row("openai", "A", "sigA"),
        # machine B: they disagree
        _row("deepseek", "B", "sigB1"),
        _row("openai", "B", "sigB2"),
    ]
    summary = gd._summary(rows, ["deepseek", "openai"])
    per = summary["per_machine"]
    assert per["A"]["signature_agreement_rate"] == 1.0
    assert per["B"]["signature_agreement_rate"] == 0.0
    # pooled over both within-machine pairs → 1 of 2 agree
    assert summary["signature_agreement_rate"] == 0.5
    # no cross-machine pair was ever formed
    assert all({p["a"], p["b"]} == {"deepseek", "openai"} for p in summary["pairwise"])
    assert {p["machine"] for p in summary["pairwise"]} == {"A", "B"}


def test_release_gate_enforces_the_floor_per_machine():
    rows = [
        _row("deepseek", "A", "s"),
        _row("openai", "A", "s"),  # A agrees
        _row("deepseek", "B", "x"),
        _row("openai", "B", "y"),  # B diverges
    ]
    errors = gd._ci_errors(rows, ["deepseek", "openai"], repeats=1, min_agreement=1.0)
    # exactly one machine fails the floor, and the message names it
    agreement_errors = [e for e in errors if "agreement" in e]
    assert len(agreement_errors) == 1
    assert "[B]" in agreement_errors[0]


def test_release_gate_expects_repeats_times_machines_rows():
    rows = [_row("deepseek", "A", "s"), _row("deepseek", "B", "s")]  # 1 machine-run each
    errors = gd._ci_errors(rows, ["deepseek"], repeats=1, min_agreement=None)
    assert errors == []  # 2 machines × 1 repeat = 2 rows, as expected
    short = [_row("deepseek", "A", "s")]  # missing machine B's run
    errors = gd._ci_errors(
        short + [_row("deepseek", "B", "s", status="error")], ["deepseek"], 1, None
    )
    assert any("failed" in e for e in errors)


# --- end-to-end with a scripted LLM (no provider, no key) ------------------


def _scripted_build_llm(routes):
    """A build_llm(prov) that returns a MockLLM routing by prompt substring.

    `routes` maps a produce-prompt substring to the produced text; the judge
    picks the first gate whose `when` substring appears in a routing table.
    """

    def build(_prov):
        def produce_fn(model, system, user, reason):
            for key, text in routes["produce"].items():
                if key in user:
                    return Produced(text=text)
            return Produced(text="ok")

        def judge_fn(model, conditions, output, context, reasoning=None):
            return routes["judge"](conditions, output)

        return MockLLM(produce_fn=produce_fn, judge_fn=judge_fn)

    return build


def test_run_once_drives_a_full_run_offline():
    # Route the spam machine down the "spam" branch deterministically.
    routes = {
        "produce": {"Classify this message": "spam", "SPAM_OK": "SPAM_OK"},
        "judge": lambda conds, out: 0,  # first gate ("...spam") fires
    }
    row = gd._run_once(
        "deepseek",
        gd.DEFAULT_CONFIG,
        machine_doc=gd.MACHINES["gate_divergence"],
        build_llm=_scripted_build_llm(routes),
    )
    assert row["skipped"] is False
    assert row["status"] == "done"
    assert row["machine"] == "gate_divergence"
    # signature records the routing decision into spam_path, then to END
    assert "label|" in row["signature"] and "spam_path" in row["signature"]
    assert row["gates"][0]["to"] == "spam_path"


def test_run_once_divergent_judges_yield_different_signatures():
    produce = {"Classify this message": "spam", "SPAM_OK": "SPAM_OK", "HAM_OK": "HAM_OK"}
    spam = gd._run_once(
        "deepseek",
        gd.DEFAULT_CONFIG,
        machine_doc=gd.MACHINES["gate_divergence"],
        build_llm=_scripted_build_llm({"produce": produce, "judge": lambda c, o: 0}),
    )
    ham = gd._run_once(
        "openai",
        gd.DEFAULT_CONFIG,
        machine_doc=gd.MACHINES["gate_divergence"],
        build_llm=_scripted_build_llm({"produce": produce, "judge": lambda c, o: 1}),
    )
    assert spam["signature"] != ham["signature"]
    summary = gd._summary([spam, ham], ["deepseek", "openai"])
    assert summary["per_machine"]["gate_divergence"]["signature_agreement_rate"] == 0.0
