"""Offline tests for scripts/repair_convergence.py — no keys, no network."""

import importlib.util

from conftest import REPO_ROOT

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
    from mklang.registry import base_registry

    registry = base_registry()
    for item in rc.CORPUS:
        machine = registry[item["machine"]]
        assert rc._repair_states(machine), f"{item['machine']} has no repair gate to measure"
        # Seeded keys must be real context keys, or the task never reaches the model.
        assert set(item["context"]) <= set(machine.context)


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
    assert [(a["attempt"], a["outcome"]) for a in row["attempts"]] == [(1, "retry"), (2, "pass")]


def test_unknown_machine_is_skipped_not_crashed():
    row = rc._run_once(
        {"id": "t", "machine": "nope", "context": {}},
        "deepseek",
        rc.DEFAULT_CONFIG,
        registry={},
    )
    assert row["skipped"] is True and "unknown machine" in row["reason"]
