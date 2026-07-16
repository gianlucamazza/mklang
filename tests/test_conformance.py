"""Reference runner for the conformance suite (conformance/README.md).

Any mklang implementation must pass these cases with its own runner; this one
binds them to the reference interpreter.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import yaml

from mklang.engine import run
from mklang.errors import JudgeUnparseable
from mklang.llm.base import Produced
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}
CASES = sorted(Path("conformance/cases").glob("*.yaml"))


class ScriptedLLM:
    """Fully case-determined LLM per the scripted-LLM contract in the README."""

    def __init__(self, spec: dict | None):
        spec = spec or {}
        produce = spec.get("produce", [])
        self._seq = list(produce) if isinstance(produce, list) else None
        self._map = dict(produce) if isinstance(produce, dict) else None
        self._judge = spec.get("judge", [])
        self._tin, self._tout = spec.get("tokens", [0, 0])
        self._lock = threading.Lock()

    def produce(self, model, system, user, reason=False, temperature=0.4, params=None) -> Produced:
        with self._lock:
            if self._map is not None:
                for key, text in self._map.items():
                    if key in user:
                        break
                else:
                    raise AssertionError(f"no scripted produce matches prompt {user[:80]!r}")
            else:
                text = self._seq.pop(0) if self._seq else "ok"
        return Produced(
            text=text,
            reasoning=("thought" if reason else None),
            input_tokens=self._tin,
            output_tokens=self._tout,
        )

    def judge(self, model, conditions, output, context, reasoning=None) -> int:
        if self._judge == "unparseable":
            raise JudgeUnparseable("scripted")
        with self._lock:
            if isinstance(self._judge, list) and self._judge:
                # Pop in order; once one entry remains, keep returning it.
                return self._judge.pop(0) if len(self._judge) > 1 else self._judge[0]
        return len(conditions) - 1


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_conformance(path):
    case = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert case["case"] == path.stem, "case name must match the filename stem"
    machine = parse_machine(case["machine"])
    registry = {machine.name: machine}
    for name, md in (case.get("registry") or {}).items():
        registry[name] = parse_machine(md)

    r = run(
        machine,
        dict(machine.context),
        registry,
        ScriptedLLM(case.get("llm")),
        TIERS,
        "judge-model",
        **(case.get("run") or {}),
    )

    exp = case["expect"]
    assert r.status == exp["status"], (r.status, r.error, r.trace)
    if "error" in exp:
        assert r.error == exp["error"]
    if "result" in exp:
        assert r.result == exp["result"]
    if "at" in exp:
        assert r.at == exp["at"]
    if "context" in exp:
        for k, v in exp["context"].items():
            assert r.context.get(k) == v, (k, r.context.get(k))
    if "trace" in exp:
        assert len(r.trace) == len(exp["trace"]), [s.get("state") for s in r.trace]
        for want, got in zip(exp["trace"], r.trace):
            for k, v in want.items():
                assert got.get(k) == v, (got.get("state"), k, got.get(k), v)
