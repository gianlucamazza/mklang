"""LLM-assisted lint (ADR 0010): instability/overlap findings from a scripted judge."""

import pytest

from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.llmlint import llm_lint_machine
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def two_gate_machine():
    return parse_machine(
        {
            "machine": "amb",
            "entry": "draft",
            "budget": 4,
            "states": {
                "draft": {
                    "structure": "a reply draft",
                    "prompt": "write it",
                    "output": "draft",
                    "gates": [
                        {
                            "when": "the draft resolves the request and is courteous",
                            "then": "ok",
                            "to": "END",
                        },
                        {"when": "the draft is acceptable", "repair": 1, "to": "draft"},
                        {"when": "otherwise", "escalate": True, "to": "draft"},
                    ],
                }
            },
        }
    )


def scripted(produce_text, judge_seq):
    """MockLLM whose judge pops `judge_seq` (sticky on the last element)."""
    seq = list(judge_seq)

    def judge_fn(model, conditions, output, context, reasoning=None):
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return MockLLM(
        produce_fn=lambda *a, **k: Produced(text=produce_text),
        judge_fn=judge_fn,
    )


def test_stable_gates_produce_no_findings():
    llm = scripted('["clear pass", "clear fail"]', [0])
    findings = llm_lint_machine(two_gate_machine(), llm, TIERS, samples=2, repeats=3)
    assert findings == []


def test_instability_and_overlap_are_reported():
    # output 1: picks 0,1,0 → unstable + overlap(0,1); output 2: stable 1,1,1
    llm = scripted('["borderline", "clear repair"]', [0, 1, 0, 1, 1, 1])
    findings = llm_lint_machine(two_gate_machine(), llm, TIERS, samples=2, repeats=3)
    assert any("unstable routing on 1/2" in f for f in findings)
    assert any("overlap on 1/2" in f and "conditions 0" in f for f in findings)


def test_unsynthesizable_state_is_skipped_with_a_finding():
    llm = scripted("no json here", [0])
    findings = llm_lint_machine(two_gate_machine(), llm, TIERS, samples=2, repeats=2)
    assert len(findings) == 1
    assert "could not synthesize" in findings[0]


def test_single_prose_or_hook_states_are_skipped():
    m = parse_machine(
        {
            "machine": "s",
            "entry": "a",
            "budget": 4,
            "hooks": ["always_true"],
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [
                        {"when": "done", "then": "ok", "to": "b"},
                        {"when": "otherwise", "then": "ok", "to": "b"},
                    ],
                },
                "b": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o2",
                    "gates": [
                        {"when": "auto", "hook": "always_true", "then": "ok", "to": "END"},
                        {"when": "needs review", "then": "ok", "to": "END"},
                        {"when": "otherwise", "then": "ok", "to": "END"},
                    ],
                },
            },
        }
    )
    calls = []
    llm = MockLLM(
        produce_fn=lambda *a, **k: calls.append(1) or Produced(text='["x"]'),
        judge_fn=lambda *a: 0,
    )
    assert llm_lint_machine(m, llm, TIERS, samples=1, repeats=1) == []
    assert calls == []  # no state qualifies → zero LLM spend


def test_cli_lint_llm_is_advisory(monkeypatch, capsys):
    from mklang import cli

    monkeypatch.setattr(
        cli, "_build_llm", lambda prov: scripted('["b1", "b2"]', [0, 1, 0, 1, 1, 1])
    )
    rc = cli.main(["lint", "examples/triage.mkl", "--llm", "--strict", "--llm-samples", "2"])
    out = capsys.readouterr().out
    assert "llm:" in out
    assert rc == 0  # --llm findings never flip the exit code, even under --strict


@pytest.mark.parametrize("kind", ["unparseable"])
def test_judge_unparseable_counts_as_no_pick(kind):
    from mklang.errors import JudgeUnparseable

    def judge_fn(model, conditions, output, context, reasoning=None):
        raise JudgeUnparseable("nonsense")

    llm = MockLLM(produce_fn=lambda *a, **k: Produced(text='["x"]'), judge_fn=judge_fn)
    findings = llm_lint_machine(two_gate_machine(), llm, TIERS, samples=1, repeats=2)
    assert findings == []  # {None} is a single stable (non-)pick, no overlap pairs
