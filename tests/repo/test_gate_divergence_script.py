"""Offline harness tests for scripts/gate_divergence.py — no keys, no network.

The release-gate helpers (`_ci_errors`, `_summary`) are also unit-tested in
test_release.py; here we cover the machine SUITE, the per-machine aggregation,
and that the harness actually drives a run end to end with a scripted LLM.
"""

import importlib.util

import pytest
from conftest import REPO_ROOT

from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.loader import semantic_check
from mklang.model import parse_machine

ROOT = REPO_ROOT


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
    assert errors == []  # 2 machines x 1 repeat = 2 rows, as expected
    short = [_row("deepseek", "A", "s")]  # missing machine B's run
    errors = gd._ci_errors(
        [*short, _row("deepseek", "B", "s", status="error")], ["deepseek"], 1, None
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
    assert row["experiment"] == "gate-divergence"
    assert len(row["input_hash"]) == 64
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


def test_input_hash_changes_when_wording_variant_changes():
    base = gd._run_once(
        "deepseek",
        gd.DEFAULT_CONFIG,
        machine_doc=gd.MACHINES["gate_divergence"],
        build_llm=_scripted_build_llm({"produce": {}, "judge": lambda c, o: 0}),
    )
    variant = gd._run_once(
        "deepseek",
        gd.DEFAULT_CONFIG,
        machine_doc=gd.paraphrase_doc("gate_divergence", gd.PARAPHRASES["gate_divergence"][0]),
        variant="p1",
        build_llm=_scripted_build_llm({"produce": {}, "judge": lambda c, o: 0}),
    )
    assert base["input_hash"] != variant["input_hash"]


# --- boundary corpus, gold routes, paraphrase variants ---------------------


@pytest.mark.parametrize("name", sorted(gd.GOLD))
def test_gold_routes_name_a_reachable_path(name):
    """A gold route must be a path the machine can actually take."""
    doc = gd.MACHINES[name]
    m = parse_machine(doc)
    for hop in gd.GOLD[name].split(" || "):
        state, to = hop.split(">")
        assert state in m.states
        assert to == "END" or to in m.states
        assert any(g.to == to for g in m.states[state].gates)


@pytest.mark.parametrize("name", sorted(gd.PARAPHRASES))
def test_paraphrase_variants_change_only_wording(name):
    """Variants must preserve the route space, or invariance is not measurable."""
    import copy

    before = copy.deepcopy(gd.MACHINES[name])
    base = parse_machine(gd.MACHINES[name])
    for variant in gd.PARAPHRASES[name]:
        m = parse_machine(gd.paraphrase_doc(name, variant))
        errors, _ = semantic_check(m, {m.name: m})
        assert errors == []
        assert set(m.states) == set(base.states)
        for sid, s in m.states.items():
            bs = base.states[sid]
            assert [g.to for g in s.gates] == [g.to for g in bs.gates]
            assert [g.kind for g in s.gates] == [g.kind for g in bs.gates]
            assert (s.prompt, s.structure) == (bs.prompt, bs.structure)
        # …and at least one condition is actually reworded.
        assert any(
            g.when != bg.when
            for sid, s in m.states.items()
            for g, bg in zip(s.gates, base.states[sid].gates, strict=True)
        )
    # Building variants never mutates the shared suite doc.
    assert gd.MACHINES[name] == before


def test_paraphrase_refuses_to_reword_the_catch_all():
    with pytest.raises(ValueError, match="otherwise"):
        gd.paraphrase_doc("none_holds", {"label": "bad", "gates": {"classify": {2: "whatever"}}})


# --- decomposed metrics ----------------------------------------------------


def _row2(provider, machine, signature, *, route=None, correct=None, variant="base"):
    row = _row(provider, machine, signature)
    row["variant"] = variant
    row["route"] = route if route is not None else signature
    row["correct"] = correct
    return row


def test_agreement_splits_cross_provider_from_self_consistency():
    """Repeats of one provider measure stability, not portability — never pooled
    into the cross-provider number."""
    rows = [
        _row2("deepseek", "A", "s1"),
        _row2("deepseek", "A", "s1"),  # deepseek is self-consistent
        _row2("openai", "A", "s2"),
        _row2("openai", "A", "s2"),  # so is openai — on a different route
    ]
    summary = gd._summary(rows, ["deepseek", "openai"])
    assert summary["intra_provider_agreement_rate"] == 1.0
    assert summary["cross_provider_agreement_rate"] == 0.0
    # The pooled number sits in between and would read as "mostly fine".
    assert summary["signature_agreement_rate"] == pytest.approx(2 / 6)


def test_intra_provider_rate_is_none_without_repeats():
    rows = [_row2("deepseek", "A", "s"), _row2("openai", "A", "s")]
    summary = gd._summary(rows, ["deepseek", "openai"])
    assert summary["intra_provider_agreement_rate"] is None
    assert summary["cross_provider_agreement_rate"] == 1.0


def test_gate_blind_spot_measures_agreement_minus_correctness():
    """Two providers can agree perfectly on the wrong route; agreement alone
    cannot see it."""
    rows = [
        _row2("deepseek", "threshold_edge", "s", route="assess>over || over>END", correct=False),
        _row2("openai", "threshold_edge", "s", route="assess>over || over>END", correct=False),
    ]
    summary = gd._summary(rows, ["deepseek", "openai"])
    assert summary["signature_agreement_rate"] == 1.0
    assert summary["accuracy"] == 0.0
    assert summary["gate_blind_spot"] == 1.0
    assert summary["per_machine"]["threshold_edge"]["accuracy"] == 0.0


def test_machines_without_gold_are_not_scored():
    rows = [
        _row2("deepseek", "sentiment_borderline", "s"),
        _row2("openai", "sentiment_borderline", "s"),
    ]
    summary = gd._summary(rows, ["deepseek", "openai"])
    assert summary["scored_runs"] == 0
    assert summary["accuracy"] is None
    assert summary["gate_blind_spot"] is None


def test_paraphrase_invariance_is_per_provider_across_wordings():
    rows = [
        # deepseek routes the same way under both wordings; openai does not.
        _row2("deepseek", "threshold_edge", "sa", route="assess>within || within>END"),
        _row2(
            "deepseek", "threshold_edge", "sb", route="assess>within || within>END", variant="p1"
        ),
        _row2("openai", "threshold_edge", "sc", route="assess>within || within>END"),
        _row2("openai", "threshold_edge", "sd", route="assess>over || over>END", variant="p1"),
    ]
    summary = gd._summary(rows, ["deepseek", "openai"])
    stats = summary["paraphrase"]["threshold_edge"]
    assert stats["cross_variant_pairs"] == 2
    assert stats["paraphrase_invariance_rate"] == 0.5
    # Variant rows never enter the headline agreement number.
    assert summary["per_machine"]["threshold_edge"]["runs_done"] == 2


def test_release_gate_can_enforce_the_decomposed_floors():
    rows = [
        _row2("deepseek", "threshold_edge", "s", route="assess>over || over>END", correct=False),
        _row2("openai", "threshold_edge", "s", route="assess>over || over>END", correct=False),
    ]
    # The pooled floor passes — agreement is perfect — while accuracy fails.
    errors = gd._ci_errors(
        rows, ["deepseek", "openai"], repeats=1, min_agreement=1.0, floors={"accuracy": 0.9}
    )
    assert any("accuracy" in e for e in errors)
    assert not any("signature agreement" in e for e in errors)
    # A floor for something this run never measured is an error, not a pass.
    errors = gd._ci_errors(
        rows, [], repeats=1, min_agreement=None, floors={"intra_provider_agreement_rate": 0.5}
    )
    assert any("was not measured" in e for e in errors)


def test_release_gate_counts_variants_as_their_own_groups():
    rows = [
        _row2("deepseek", "A", "s"),
        _row2("deepseek", "A", "s", variant="p1"),
    ]
    assert gd._ci_errors(rows, ["deepseek"], repeats=1, min_agreement=None) == []
    # deepseek ran the base machine but not the variant: 1 of the 2 expected rows.
    partial = [_row2("deepseek", "A", "s"), _row2("openai", "A", "s", variant="p1")]
    assert gd._ci_errors(partial, ["deepseek"], repeats=1, min_agreement=None)


def test_run_once_scores_the_none_verdict_route_as_correct():
    """`none_holds` is only routable through the judge's "none of the above"
    verdict — the machine that measures what SPEC §5 totality bought."""
    routes = {
        "produce": {"MAINTENANCE WINDOW": "MAINTENANCE WINDOW SCHEDULED FOR SUNDAY"},
        "judge": lambda conds, out: len(conds),  # none of the listed conditions holds
    }
    row = gd._run_once(
        "deepseek",
        gd.DEFAULT_CONFIG,
        machine_doc=gd.MACHINES["none_holds"],
        build_llm=_scripted_build_llm(routes),
    )
    assert row["status"] == "done"
    assert row["route"] == gd.GOLD["none_holds"]
    assert row["correct"] is True
    assert row["variant"] == "base"


def test_run_once_marks_a_forced_wrong_route_incorrect():
    routes = {
        "produce": {"MAINTENANCE WINDOW": "MAINTENANCE WINDOW SCHEDULED FOR SUNDAY"},
        "judge": lambda conds, out: 0,  # forced choice: "failed payment" wins anyway
    }
    row = gd._run_once(
        "openai",
        gd.DEFAULT_CONFIG,
        machine_doc=gd.MACHINES["none_holds"],
        build_llm=_scripted_build_llm(routes),
        variant="p1",
    )
    assert row["correct"] is False
    assert row["variant"] == "p1"
