"""Scripted-LLM test harness: the single source of truth for deterministic,
API-key-free testing of mklang machines.

Two consumers share this module:

- **The conformance suite** (`tests/test_conformance.py`) — pins the *interpreter*
  against `conformance/cases/*.yaml` (SPEC §5–§7). It builds a machine + registry
  from each case and asserts the expectation matches.
- **`mklang test`** (the CLI) — lets an *author* test their own `.mk` against a
  script of named scenarios, without a provider or API key.

Everything the two share lives here exactly once: the scripted LLM (produce
list/map, tokens, judge sequence / "unparseable"), the scripted `hooks:`/`tools:`
bindings, and the expectation matcher (status, error, `error_prefix`, result,
`at`, trace skeleton, context keys). The scenario/case format is identical:

```yaml
llm:   { produce: [...], judge: [...], tokens: [in, out] }
tools: { name: [...] | {input-substring: output} }
hooks: { name: [bool, ...] }
input: { key: value }   # host-supplied context — tainted by provenance (ADR 0025)
run:   { cost_budget: N, on_truncate: report|halt }  # optional interpreter options
expect:
  status: done | halt            # required
  error / error_prefix / result / at / context / trace   # optional
```

See `conformance/README.md` for the full contract.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass

from .engine import RunResult, run
from .errors import JudgeUnparseable
from .llm.base import Produced
from .model import Machine, parse_machine

# All tiers collapse to one model: scripted judges/producers ignore the model
# name, so a single mapping keeps every case provider-neutral.
TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


class ScriptedLLM:
    """Fully scenario-determined LLM per the scripted-LLM contract (README)."""

    def __init__(self, spec: dict | None):
        spec = spec or {}
        produce = spec.get("produce", [])
        self._seq = list(produce) if isinstance(produce, list) else None
        self._map = dict(produce) if isinstance(produce, dict) else None
        self._judge = spec.get("judge", [])
        self._tin, self._tout = spec.get("tokens", [0, 0])
        self._lock = threading.Lock()

    def produce(
        self,
        model: str,
        system: str,
        user: str,
        reason: bool = False,
        temperature: float = 0.4,
        params: dict | None = None,
    ) -> Produced:
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

    def judge(
        self,
        model: str,
        conditions: list[str],
        output: str,
        context: dict,
        reasoning: str | None = None,
    ) -> int:
        if self._judge == "unparseable":
            raise JudgeUnparseable("scripted")
        with self._lock:
            if isinstance(self._judge, list) and self._judge:
                # Pop in order; once one entry remains, keep returning it.
                return self._judge.pop(0) if len(self._judge) > 1 else self._judge[0]
        return len(conditions) - 1


class _ScriptedSeq:
    """Shared driver for scripted hook/tool sequences: pop in order, keep the last."""

    def __init__(self, name: str, seq: list):
        self.name = name
        self._seq = list(seq)
        self._lock = threading.Lock()

    def _next(self):
        with self._lock:
            if not self._seq:
                raise AssertionError(f"scripted {self.name!r} invoked with no values left")
            return self._seq.pop(0) if len(self._seq) > 1 else self._seq[0]


class _ScriptedHook(_ScriptedSeq):
    """A gate hook `(ctx, output) -> bool` driven by a scripted boolean sequence."""

    def __call__(self, _ctx: dict, _output: object) -> bool:
        return bool(self._next())


class _ScriptedTool:
    """A tool `(dict) -> str`: a sequential list, or a {input-substring: output} map."""

    def __init__(self, name: str, spec: dict | list):
        self.name = name
        self._map = dict(spec) if isinstance(spec, dict) else None
        self._seq = None if self._map is not None else _ScriptedSeq(name, list(spec))

    def __call__(self, inp: dict) -> str:
        if self._map is not None:
            blob = json.dumps(inp, ensure_ascii=False)
            for key, out in self._map.items():
                if key in blob:
                    return str(out)
            raise AssertionError(f"tool {self.name!r}: no scripted output for input {inp!r}")
        # Exactly one of _map/_seq is set (see __init__).
        assert self._seq is not None
        return str(self._seq._next())


def scripted_hooks(spec: dict | None) -> dict:
    """Build a name -> callable hook registry from a scenario's `hooks:` block."""
    return {name: _ScriptedHook(name, seq) for name, seq in (spec or {}).items()}


def scripted_tools(spec: dict | None) -> dict:
    """Build a name -> callable tool registry from a scenario's `tools:` block."""
    return {name: _ScriptedTool(name, s) for name, s in (spec or {}).items()}


def build_registry(case: dict) -> tuple[Machine, dict]:
    """Parse a conformance case's inline `machine:` (+ optional `registry:`)."""
    machine = parse_machine(case["machine"])
    registry = {machine.name: machine}
    for name, md in (case.get("registry") or {}).items():
        registry[name] = parse_machine(md)
    return machine, registry


def run_scenario(
    machine: Machine, registry: dict, scenario: dict, tiers: dict | None = None
) -> RunResult:
    """Execute `machine` under a scenario's scripted LLM/tools/hooks/run options.

    The scenario is a dict with optional `llm`, `tools`, `hooks`, `input`, and
    `run` keys — the shared conformance/scenario format. `input:` merges
    host-supplied values over the machine's `context:`; the engine's provenance
    rule marks them tainted (ADR 0025), so cases can exercise host-input
    delimiting. Judging follows each state's tier (SPEC §2.1); with the
    collapsed `TIERS` map every tier resolves to one model.
    """
    return run(
        machine,
        {**machine.context, **(scenario.get("input") or {})},
        registry,
        ScriptedLLM(scenario.get("llm")),
        tiers or TIERS,
        None,  # no global judge override — judging follows each state's tier
        tools=scripted_tools(scenario.get("tools")),
        hooks=scripted_hooks(scenario.get("hooks")),
        **(scenario.get("run") or {}),
    )


@dataclass
class Mismatch:
    """One expectation that did not hold: `key` names it, with expected vs actual."""

    key: str
    expected: object
    actual: object

    def __str__(self) -> str:
        return f"{self.key}: expected {self.expected!r}, got {self.actual!r}"


def match_expectation(result: RunResult, expect: dict) -> list[Mismatch]:
    """Compare a RunResult against an `expect:` block; return ordered mismatches.

    Empty list ⇔ the scenario passed. The order (status, error, error_prefix,
    result, at, context, trace) is deterministic, so `mismatches[0]` is the first
    mismatched key — what `mklang test` shows as the minimal diff. Trace matching
    is a skeleton: same length, and each listed key must equal the step's value.
    """
    ms: list[Mismatch] = []
    if "status" in expect and result.status != expect["status"]:
        ms.append(Mismatch("status", expect["status"], result.status))
    if "error" in expect and result.error != expect["error"]:
        ms.append(Mismatch("error", expect["error"], result.error))
    if "error_prefix" in expect:
        pref = expect["error_prefix"]
        if not (result.error and result.error.startswith(pref)):
            ms.append(Mismatch("error_prefix", pref, result.error))
    if "result" in expect and result.result != expect["result"]:
        ms.append(Mismatch("result", expect["result"], result.result))
    if "at" in expect and result.at != expect["at"]:
        ms.append(Mismatch("at", expect["at"], result.at))
    if "context" in expect:
        for k, v in expect["context"].items():
            got = result.context.get(k)
            if got != v:
                ms.append(Mismatch(f"context.{k}", v, got))
    if "trace" in expect:
        want_trace = expect["trace"]
        if len(result.trace) != len(want_trace):
            ms.append(
                Mismatch(
                    "trace.length",
                    len(want_trace),
                    f"{len(result.trace)} ({[s.get('state') for s in result.trace]})",
                )
            )
        else:
            for i, (want, got) in enumerate(zip(want_trace, result.trace)):
                for k, v in want.items():
                    if got.get(k) != v:
                        ms.append(Mismatch(f"trace[{i}].{k}", v, got.get(k)))
    return ms
