#!/usr/bin/env python3
"""Does `repair(N)` converge, or is the budget doing all the work?

`repair` re-enters a state with the failed `when` appended as feedback. The
language's claim is that the feedback makes attempt 2 better than attempt 1. That
claim has never been measured. If the pass rate does **not** rise with the
attempt index, the feedback is decoration and the only thing buying reliability
is the extra sample — at a cost linear in tokens.

Metric (per state with a `repair` gate, pooled per machine and overall):

    p(k) = passes at attempt k / runs that reached attempt k
    lift = p(2) - p(1)

`lift > 0` is the language's claim. `lift ≈ 0` means resampling, not repairing.
`lift < 0` means the attempts that survive to k are simply the harder ones —
which is also the standing caveat on this measurement: attempt k is conditioned
on having failed k-1 times, so the population gets harder as k grows. That
selection effect biases `lift` **downwards**, so a positive lift is evidence and
a slightly negative one is not yet a refutation.

Usage:
  uv run python scripts/repair_convergence.py --provider deepseek --repeats 5
  uv run python scripts/repair_convergence.py --machines std_refine --jsonl out.jsonl
  uv run python scripts/repair_convergence.py --self-check    # offline, no keys

See docs/experiments/repair-convergence.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from mklang.cli import _build_llm
from mklang.config import ProviderConfig, load_provider
from mklang.engine import run
from mklang.llm.base import LLM
from mklang.model import Machine
from mklang.registry import base_registry

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = str(ROOT / "config" / "runtime.example.yaml")

# Tasks chosen so a first draft plausibly misses the criteria: the repair gate
# must actually fire, or the measurement has nothing to measure. Every entry
# names a bundled machine (registry lookup) plus the context to seed.
CORPUS: list[dict] = [
    {
        "id": "refine_format",
        "machine": "std_refine",
        "context": {
            "task": "Explain what a state machine is to a new engineer.",
            "criteria": (
                "exactly three bullet points; each bullet is under twelve words; "
                "each bullet starts with a verb; the last line is exactly DONE"
            ),
        },
    },
    {
        "id": "refine_grounding",
        "machine": "std_refine",
        "context": {
            "task": (
                "Answer this customer using only this fact: the return window is "
                "30 days from delivery. Customer asks: how long do I have to return?"
            ),
            "criteria": (
                "states 30 days explicitly; mentions that it runs from delivery; "
                "adds no policy detail that is not in the given fact; at most two sentences"
            ),
        },
    },
    {
        "id": "refine_constraint",
        "machine": "std_refine",
        "context": {
            "task": "Write a release note for a bug fix in the gate judge.",
            "criteria": (
                "under 40 words; names the affected component; states the user-visible "
                "change; contains no adjectives of praise"
            ),
        },
    },
]


def _repair_states(machine: Machine) -> set[str]:
    """States whose gate list contains a `repair` — the only ones with attempts."""
    return {sid for sid, s in machine.states.items() if any(g.kind == "repair" for g in s.gates)}


def attempts_from_trace(trace: list[dict], repair_states: set[str]) -> list[dict]:
    """Turn a trace into one row per (state, attempt index) with its outcome.

    Attempt k of a state is its k-th execution in the run. The outcome is read
    from the gate that fired: `repair` means the attempt was rejected, `ok` means
    it passed, `escalate`/`fail` means the state gave up (usually the budget)."""
    seen: dict[str, int] = {}
    rows = []
    for step in trace:
        state = step.get("state")
        if state not in repair_states:
            continue
        seen[state] = seen.get(state, 0) + 1
        policy = step.get("policy")
        outcome = {"repair": "retry", "ok": "pass"}.get(str(policy), "give-up")
        rows.append({"state": state, "attempt": seen[state], "outcome": outcome})
    return rows


def _run_once(
    item: dict,
    provider_name: str,
    config: str,
    build_llm: Callable[[ProviderConfig], LLM] = _build_llm,
    registry: dict | None = None,
) -> dict:
    """One machine run; returns a row with the per-attempt outcomes."""
    reg = registry if registry is not None else base_registry()
    machine = reg.get(item["machine"])
    if machine is None:
        return {"item": item["id"], "skipped": True, "reason": f"unknown machine {item['machine']}"}
    prov = load_provider(config, provider_name)
    if build_llm is _build_llm and not prov.api_key and prov.name != "local":
        return {"item": item["id"], "skipped": True, "reason": "no API key"}
    result = run(
        machine,
        {**machine.context, **item["context"]},
        reg,
        build_llm(prov),
        prov.tiers,
        prov.judge_override(),
        tier_params=prov.params,
        cost_budget=40_000,
    )
    rows = attempts_from_trace(result.trace or [], _repair_states(machine))
    return {
        "item": item["id"],
        "machine": machine.name,
        "provider": provider_name,
        "skipped": False,
        "status": result.status,
        "error": result.error,
        "attempts": rows,
        "max_attempt": max((r["attempt"] for r in rows), default=0),
        "usage": result.usage,
    }


def summarize(rows: list[dict]) -> dict:
    """Pass rate per attempt index, per machine and pooled."""
    done = [r for r in rows if not r.get("skipped")]
    per_machine: dict[str, dict] = {}
    pooled: dict[int, dict[str, int]] = {}
    for row in done:
        bucket = per_machine.setdefault(row.get("machine") or "unknown", {})
        for attempt in row["attempts"]:
            k = attempt["attempt"]
            for target in (
                bucket.setdefault(k, {"reached": 0, "passed": 0}),
                pooled.setdefault(k, {"reached": 0, "passed": 0}),
            ):
                target["reached"] += 1
                target["passed"] += attempt["outcome"] == "pass"

    def rates(counts: dict[int, dict[str, int]]) -> dict:
        by_attempt = {
            str(k): {
                "reached": c["reached"],
                "passed": c["passed"],
                "pass_rate": (c["passed"] / c["reached"]) if c["reached"] else None,
            }
            for k, c in sorted(counts.items())
        }
        first, second = counts.get(1), counts.get(2)
        lift = None
        if first and second and first["reached"] and second["reached"]:
            lift = round(
                second["passed"] / second["reached"] - first["passed"] / first["reached"], 4
            )
        return {"by_attempt": by_attempt, "lift_attempt_2_over_1": lift}

    summary = {
        "runs": len(done),
        "runs_skipped": sum(1 for r in rows if r.get("skipped")),
        "runs_failed": sum(1 for r in done if r.get("status") != "done"),
        "per_machine": {name: rates(counts) for name, counts in per_machine.items()},
        **rates(pooled),
    }
    summary["verdict"] = _verdict(summary["lift_attempt_2_over_1"], pooled.get(2))
    return summary


def _verdict(lift: float | None, second: dict[str, int] | None) -> str:
    if lift is None or not second or second["reached"] < 5:
        return "not measured: too few runs reached a second attempt"
    if lift > 0.05:
        return "converging: the feedback makes the retry better than the first try"
    if lift < -0.05:
        return (
            "no convergence: later attempts pass LESS often — consistent with the "
            "selection effect, but no evidence the feedback helps"
        )
    return "flat: repair is resampling, not repairing — the budget is doing the work"


class _ScriptedFailThenPass:
    """Offline LLM for --self-check: the judge rejects the first attempt of each
    state and accepts the second, so the harness's attempt bookkeeping is
    exercised without a provider."""

    def __init__(self) -> None:
        self.seen: dict[str, int] = {}

    def produce(self, model, system, user, reason=False, temperature=0.4, params=None):
        from mklang.llm.base import Produced

        return Produced(text="draft")

    def judge(self, model, conditions, output, context, reasoning=None, allow_none=False):
        key = "|".join(conditions)
        self.seen[key] = self.seen.get(key, 0) + 1
        # Condition 0 is "satisfies every criterion", condition 1 is the repair.
        return 0 if self.seen[key] > 1 else min(1, len(conditions) - 1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=DEFAULT_CONFIG, help="runtime YAML")
    p.add_argument("--provider", default="deepseek", help="provider name (needs a key)")
    p.add_argument("--repeats", type=int, default=3, help="runs per corpus item")
    p.add_argument(
        "--machines",
        default="",
        help="comma-separated machine names to keep from the corpus (default: all)",
    )
    p.add_argument("--jsonl", type=Path, default=None, help="append raw rows here")
    p.add_argument("--summary-json", type=Path, default=None, help="write the summary JSON here")
    p.add_argument(
        "--self-check",
        action="store_true",
        help="offline run with a scripted fail-then-pass judge (no keys, no network) — "
        "checks the harness, not the language claim",
    )
    args = p.parse_args(argv)
    if args.repeats < 1:
        p.error("--repeats must be at least 1")

    keep = {x.strip() for x in args.machines.split(",") if x.strip()}
    corpus = [i for i in CORPUS if not keep or i["machine"] in keep]
    if not corpus:
        p.error(f"--machines selected nothing (have: {sorted({i['machine'] for i in CORPUS})})")

    build = (lambda _prov: _ScriptedFailThenPass()) if args.self_check else _build_llm
    rows: list[dict] = []
    for item in corpus:
        for i in range(args.repeats):
            try:
                row = _run_once(item, args.provider, args.config, build_llm=build)
            except Exception as e:
                row = {
                    "item": item["id"],
                    "machine": item["machine"],
                    "skipped": False,
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                    "attempts": [],
                }
            row["repeat"] = i
            rows.append(row)
            tag = f"{item['id']}[{i}]"
            if row.get("skipped"):
                print(f"# skip {tag}: {row.get('reason')}", file=sys.stderr)
            else:
                print(
                    f"{tag}: status={row.get('status')} attempts={row.get('max_attempt')}",
                    file=sys.stderr,
                )
            if args.jsonl:
                with args.jsonl.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = summarize(rows)
    if args.self_check:
        summary["note"] = "offline self-check: scripted judge, not evidence about any provider"
    rendered = json.dumps(summary, indent=2, ensure_ascii=False)
    print(rendered)
    if args.summary_json:
        args.summary_json.write_text(rendered + "\n", encoding="utf-8")
    return 0 if summary["runs"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
