"""Gated live smoke — opt-in via MKLANG_LIVE=1, provider-agnostic.

Runs against the config's `active` provider (override with MKLANG_LIVE_PROVIDER)
and skips when its API key is missing. Every provider — Anthropic included — goes
through the same path with whatever models the runtime config maps; no
provider-specific test code.
"""

import os

import pytest

from mklang.cli import _build_llm
from mklang.config import load_provider
from mklang.engine import run
from mklang.model import parse_machine

pytestmark = pytest.mark.skipif(
    os.environ.get("MKLANG_LIVE") != "1",
    reason="live smoke is opt-in: set MKLANG_LIVE=1 (and optionally MKLANG_LIVE_PROVIDER)",
)

CONFIG = "config/runtime.example.yaml"


def _provider():
    prov = load_provider(CONFIG, os.environ.get("MKLANG_LIVE_PROVIDER"))
    if not prov.api_key and prov.name != "local":
        pytest.skip(f"no API key for provider {prov.name!r}")
    return prov


def test_live_smoke_produce_and_judge():
    """One generative state + one prose gate: exercises produce AND the judge."""
    prov = _provider()
    m = parse_machine(
        {
            "machine": "live_smoke",
            "entry": "ack",
            "budget": 3,
            "states": {
                "ack": {
                    "structure": "The single word OK.",
                    "prompt": "Reply with exactly the single word OK.",
                    "output": "o",
                    "gates": [
                        {
                            "when": "the output is a short acknowledgement",
                            "then": "ok",
                            "to": "END",
                        },
                        {"when": "otherwise", "then": "ok", "to": "END"},
                    ],
                },
            },
        }
    )
    r = run(
        m,
        dict(m.context),
        {m.name: m},
        _build_llm(prov),
        prov.tiers,
        prov.judge_model(),
        tier_params=prov.params,
        cost_budget=30_000,
    )
    assert r.status == "done", (prov.name, r.error, r.trace)
    assert r.usage["output_tokens"] > 0
