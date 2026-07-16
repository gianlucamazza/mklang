"""Remediation 002: per-state judge tier (F1) and sample-branch index (F3)."""

from mklang.engine import run
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine

# Distinct model per tier so we can tell which one judged a given state's gates.
TIERS = {"fast": "F", "balanced": "B", "reasoning": "R"}


def _two_tier_machine():
    return parse_machine(
        {
            "machine": "jt",
            "entry": "a",
            "budget": 5,
            "states": {
                # fast generation → its gate must be judged by the fast model
                "a": {
                    "structure": "s",
                    "prompt": "p",
                    "tier": "fast",
                    "output": "o",
                    "gates": [{"when": "the output is fine", "then": "ok", "to": "b"}],
                },
                # reasoning generation → its high-stakes gate must be judged by the
                # reasoning model, not silently downgraded to fast (F1 / SPEC §2.1).
                "b": {
                    "structure": "s",
                    "prompt": "p",
                    "tier": "reasoning",
                    "output": "o2",
                    "gates": [{"when": "the matter is resolved", "then": "ok", "to": "END"}],
                },
            },
        }
    )


def test_judge_follows_each_state_tier_by_default():
    m = _two_tier_machine()
    llm = MockLLM(judge_fn=lambda *a: 0)  # first (only) prose gate fires
    r = run(m, {}, {m.name: m}, llm, TIERS)  # no judge override → tier-following
    assert r.status == "done"
    # Two prose-gate judgements, judged by two DIFFERENT models (fast then reasoning).
    assert [c["model"] for c in llm.judge_calls] == ["F", "R"]
    # The chosen judge model is traced whenever gate_via == llm (F1.4).
    judged = [s for s in r.trace if s.get("gate_via") == "llm"]
    assert [s["judge_model"] for s in judged] == ["F", "R"]


def test_judge_override_wins_for_all_states():
    m = _two_tier_machine()
    llm = MockLLM(judge_fn=lambda *a: 0)
    r = run(m, {}, {m.name: m}, llm, TIERS, "OVERRIDE")  # global judge: override
    assert r.status == "done"
    assert [c["model"] for c in llm.judge_calls] == ["OVERRIDE", "OVERRIDE"]
    judged = [s for s in r.trace if s.get("gate_via") == "llm"]
    assert all(s["judge_model"] == "OVERRIDE" for s in judged)


def test_sample_branches_receive_distinct_index():
    seen: list[str] = []

    def produce(model, system, user, reason):
        seen.append(user)
        return Produced("cand")

    m = parse_machine(
        {
            "machine": "toct",
            "entry": "explore",
            "budget": 6,
            "states": {
                "explore": {
                    "structure": "one candidate",
                    "prompt": "You are branch {{index}}; propose an approach.",
                    "sample": 3,
                    "output": "candidates",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    r = run(m, {}, {m.name: m}, MockLLM(produce_fn=produce), TIERS)
    assert r.status == "done"
    # Each of the three sample branches rendered {{index}} to its own 0-based number.
    rendered = sorted(seen)
    assert rendered == [
        "You are branch 0; propose an approach.",
        "You are branch 1; propose an approach.",
        "You are branch 2; propose an approach.",
    ]
