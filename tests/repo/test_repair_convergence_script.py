"""Offline tests for scripts/repair_convergence.py — no keys, no network."""

import importlib.util
import json

import pytest
from conftest import REPO_ROOT

from mklang.loader import semantic_check
from mklang.model import parse_machine

ROOT = REPO_ROOT


def _module():
    spec = importlib.util.spec_from_file_location(
        "repair_convergence", ROOT / "scripts" / "repair_convergence.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = _module()


def test_corpus_names_machines_that_exist_and_can_repair():
    registry = rc._registry()
    for item in rc.CORPUS:
        machine = registry[item["machine"]]
        assert rc._repair_states(machine), f"{item['machine']} has no repair gate to measure"
        # Seeded keys must be real context keys, or the task never reaches the model.
        assert set(item["context"]) <= set(machine.context)


@pytest.mark.parametrize("name", list(rc.MACHINES))
def test_every_experiment_machine_is_valid_and_can_repair(name):
    machine = parse_machine(rc.MACHINES[name])
    errors, _ = semantic_check(machine, {machine.name: machine})
    assert errors == []
    assert machine.name == name
    assert rc._repair_states(machine), f"{name} has no repair gate to measure"


@pytest.mark.parametrize("name", list(rc.MACHINES))
def test_an_exhausted_repair_gives_up_instead_of_passing(name):
    # `attempts_from_trace` reads `ok` as a pass, so a machine whose catch-all
    # says `then: ok` would report its own failures as successes. Every repair
    # state must leave through an escalate/fail instead.
    machine = parse_machine(rc.MACHINES[name])
    for sid in rc._repair_states(machine):
        assert machine.states[sid].gates[-1].kind in {"escalate", "fail"}


def test_the_corpus_covers_more_than_one_machine():
    # ADR 0031 §3 counts machines, not tasks: three items on one machine cannot
    # evaluate its condition in either direction.
    assert len({item["machine"] for item in rc.CORPUS}) >= 3


def test_self_check_over_the_whole_corpus_reaches_a_second_attempt(capsys):
    # The structural half of issue #93: before spending anything live, the corpus
    # must be able to reach attempt 2 often enough for `_verdict` to say something
    # other than "not measured" (its floor is five second attempts).
    assert rc.main(["--self-check", "--repeats", "2"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["by_attempt"]["2"]["reached"] >= 5


def test_attempts_are_numbered_per_state_and_read_the_fired_gate():
    trace = [
        {"state": "draft", "policy": "repair", "to": "draft"},
        {"state": "draft", "policy": "repair", "to": "draft"},
        {"state": "draft", "policy": "ok", "to": "END"},
        {"state": "sink", "policy": "ok", "to": "END"},  # not a repair state: ignored
    ]
    rows = rc.attempts_from_trace(trace, {"draft"})
    assert [(r["attempt"], r["outcome"]) for r in rows] == [
        (1, "retry"),
        (2, "retry"),
        (3, "pass"),
    ]


def test_exhausted_repair_reads_as_give_up_not_pass():
    trace = [
        {"state": "draft", "policy": "repair", "to": "draft"},
        {"state": "draft", "policy": "escalate", "to": "flag"},
    ]
    rows = rc.attempts_from_trace(trace, {"draft"})
    assert [r["outcome"] for r in rows] == ["retry", "give-up"]


def _row(outcomes, machine="m"):
    return {
        "machine": machine,
        "skipped": False,
        "status": "done",
        "attempts": [
            {"state": "draft", "attempt": i + 1, "outcome": o} for i, o in enumerate(outcomes)
        ],
    }


def test_lift_is_the_claim_under_test():
    # Six runs: all fail the first attempt, all pass the second.
    summary = rc.summarize([_row(["retry", "pass"]) for _ in range(6)])
    assert summary["by_attempt"]["1"]["pass_rate"] == 0.0
    assert summary["by_attempt"]["2"]["pass_rate"] == 1.0
    assert summary["lift_attempt_2_over_1"] == 1.0
    assert summary["verdict"].startswith("converging")


def test_flat_repair_is_called_theatre_not_convergence():
    # Every attempt fails at the same rate: the budget, not the feedback, wins.
    rows = [_row(["retry", "retry", "give-up"]) for _ in range(6)]
    summary = rc.summarize(rows)
    assert summary["lift_attempt_2_over_1"] == 0.0
    assert "resampling" in summary["verdict"]


def test_too_few_second_attempts_is_not_measured():
    summary = rc.summarize([_row(["pass"]) for _ in range(6)])
    assert summary["lift_attempt_2_over_1"] is None
    assert summary["verdict"].startswith("not measured")


def test_run_once_drives_a_repair_loop_offline():
    machine = parse_machine(
        {
            "machine": "tiny_refine",
            "entry": "draft",
            "budget": 5,
            "context": {"task": ""},
            "states": {
                "draft": {
                    "structure": "s",
                    "prompt": "do {{task}}",
                    "output": "answer",
                    "gates": [
                        {"when": "the answer is good", "then": "ok", "to": "END"},
                        {"when": "the answer falls short", "repair": 2, "to": "draft"},
                        {"when": "otherwise", "then": "ok", "to": "END"},
                    ],
                }
            },
        }
    )
    row = rc._run_once(
        {"id": "t", "machine": "tiny_refine", "context": {"task": "x"}},
        "deepseek",
        rc.DEFAULT_CONFIG,
        build_llm=lambda _prov: rc._ScriptedFailThenPass(),
        registry={"tiny_refine": machine},
    )
    assert row["status"] == "done"
    assert row["experiment"] == "repair-convergence"
    assert len(row["input_hash"]) == 64
    assert [(a["attempt"], a["outcome"]) for a in row["attempts"]] == [(1, "retry"), (2, "pass")]


def test_unknown_machine_is_skipped_not_crashed():
    row = rc._run_once(
        {"id": "t", "machine": "nope", "context": {}},
        "deepseek",
        rc.DEFAULT_CONFIG,
        registry={},
    )
    assert row["skipped"] is True and "unknown machine" in row["reason"]
