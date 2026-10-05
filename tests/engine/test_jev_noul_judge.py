"""Engine integration: Jev Noul judge walks first-true, including priority_shadow."""

from __future__ import annotations

import json
from pathlib import Path

from mklang.engine import run
from mklang.llm.base import Produced
from mklang.llm.jev import MAPPING, JevNoulJudge, JudgeRoutedLLM
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "llm/fixtures/jev/priority_shadow.json").read_text(
        encoding="utf-8"
    )
)

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def _priority_shadow_machine():
    return parse_machine(
        {
            "machine": "priority_shadow",
            "entry": "draft",
            "budget": 4,
            "default_tier": "fast",
            "result": "outcome",
            "states": {
                "draft": {
                    "structure": 'The single line "REFUND 2000 EUR APPROVED FOR ORDER 71".',
                    "prompt": "Reply with exactly: REFUND 2000 EUR APPROVED FOR ORDER 71",
                    "output": "reply",
                    "gates": [
                        {"when": "the reply mentions a refund", "then": "ok", "to": "broad"},
                        {
                            "when": "the reply mentions a refund above 1000 EUR",
                            "then": "ok",
                            "to": "narrow",
                        },
                        {"when": "otherwise", "then": "ok", "to": "neither"},
                    ],
                },
                "broad": {
                    "structure": 'The word "BROAD".',
                    "prompt": "Reply with exactly BROAD",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
                "narrow": {
                    "structure": 'The word "NARROW".',
                    "prompt": "Reply with exactly NARROW",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
                "neither": {
                    "structure": 'The word "NEITHER".',
                    "prompt": "Reply with exactly NEITHER",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )


def test_engine_priority_shadow_uses_noul_first_true_not_choice():
    payloads: list[dict] = []

    def post(_url: str, payload: dict) -> dict:
        payloads.append(payload)
        return FIXTURE

    produce = MockLLM(produce_fn=lambda *a: Produced("REFUND 2000 EUR APPROVED FOR ORDER 71"))
    llm = JudgeRoutedLLM(produce, JevNoulJudge("test-key", post=post))
    machine = _priority_shadow_machine()
    r = run(machine, {}, {machine.name: machine}, llm, TIERS)
    assert r.status == "done"
    draft = r.trace[0]
    assert draft["to"] == "broad"
    assert draft["gate_via"] == "llm"
    assert draft["judge_mapping"] == MAPPING
    assert draft["noul_probs"] == [0.71, 0.99]
    assert draft["jev_threshold"] == 0.5
    assert draft["fence_applied"] is True
    assert "judge_parse" not in draft
    assert payloads[0]["questions"]["g0"]["type"] == "noul"
    assert "choice" not in json.dumps(payloads[0]["questions"])
