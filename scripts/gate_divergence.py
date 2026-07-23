#!/usr/bin/env python3
"""Measure cross-provider gate agreement on a fixed machine + inputs.

Syntactic portability ("same .mkl, any provider") does not imply semantic
agreement on which prose gate fires. This script runs a small routing machine
once per provider (with API key) and reports pairwise agreement on the
gate-trace signature.

Usage:
  uv run python scripts/gate_divergence.py
  uv run python scripts/gate_divergence.py --providers deepseek,openai --repeats 3
  uv run python scripts/gate_divergence.py --jsonl results.jsonl
  uv run python scripts/gate_divergence.py --repeats 3 \
    --require-providers deepseek,openai --min-agreement 1.0 \
    --summary-json summary.json

Requires keys in .env (same as `mklang run`). Skips providers without a key.
See docs/experiments/gate-divergence.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from itertools import combinations
from pathlib import Path

from mklang.cli import _build_llm
from mklang.config import load_provider
from mklang.engine import run
from mklang.model import parse_machine

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = str(ROOT / "config" / "runtime.example.yaml")

# A suite of small synthetic machines, each stressing a DIFFERENT gate shape so
# the experiment measures more than one kind of judge decision. Every machine is
# fast-tier throughout and terminates in a few steps. Agreement is always
# computed WITHIN a machine (cross-machine signatures differ by construction).
#
# `gate_divergence` is kept verbatim and stays the default single machine so the
# release gate (release.yml) and its pinned history remain comparable.
MACHINES: dict[str, dict] = {
    # 1) Multi-way `ok` routing on a categorical label.
    "gate_divergence": {
        "machine": "gate_divergence",
        "entry": "label",
        "budget": 5,
        "default_tier": "fast",
        "states": {
            "label": {
                "structure": 'Exactly one word: "spam", "ham", or "unknown".',
                "prompt": (
                    "Classify this message as spam, ham, or unknown. "
                    "Reply with exactly one of those three words.\n"
                    "Message: Congratulations! You won a free prize. Click here now."
                ),
                "output": "tag",
                "gates": [
                    {"when": 'the output is the word "spam"', "then": "ok", "to": "spam_path"},
                    {"when": 'the output is the word "ham"', "then": "ok", "to": "ham_path"},
                    {"when": "otherwise", "then": "ok", "to": "other_path"},
                ],
            },
            "spam_path": {
                "structure": 'The single word "SPAM_OK".',
                "prompt": "Reply with exactly SPAM_OK",
                "output": "done_msg",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "ham_path": {
                "structure": 'The single word "HAM_OK".',
                "prompt": "Reply with exactly HAM_OK",
                "output": "done_msg",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "other_path": {
                "structure": 'The single word "OTHER_OK".',
                "prompt": "Reply with exactly OTHER_OK",
                "output": "done_msg",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
        },
    },
    # 2) Borderline judgement: a deliberately mixed-signal review, so the
    # positive/negative/mixed gates are genuinely contestable across judges.
    "sentiment_borderline": {
        "machine": "sentiment_borderline",
        "entry": "assess",
        "budget": 4,
        "default_tier": "fast",
        "states": {
            "assess": {
                "structure": "One or two sentences describing the reviewer's sentiment.",
                "prompt": (
                    "Summarize the sentiment of this product review in one line.\n"
                    "Review: The build quality is excellent and it feels premium, but it "
                    "died after three days and support never replied."
                ),
                "output": "reading",
                "gates": [
                    {
                        "when": "the sentiment is clearly positive overall",
                        "then": "ok",
                        "to": "pos",
                    },
                    {
                        "when": "the sentiment is clearly negative overall",
                        "then": "ok",
                        "to": "neg",
                    },
                    {"when": "otherwise", "then": "ok", "to": "mixed"},
                ],
            },
            "pos": {
                "structure": 'The word "POSITIVE".',
                "prompt": "Reply with exactly POSITIVE",
                "output": "verdict",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "neg": {
                "structure": 'The word "NEGATIVE".',
                "prompt": "Reply with exactly NEGATIVE",
                "output": "verdict",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "mixed": {
                "structure": 'The word "MIXED".',
                "prompt": "Reply with exactly MIXED",
                "output": "verdict",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
        },
    },
    # 3) Control-flow-critical gate: an `escalate` on "severe" decides whether a
    # human is looped in. Divergence here is the costly kind (SPEC §11).
    "severity_escalate": {
        "machine": "severity_escalate",
        "entry": "triage",
        "budget": 4,
        "default_tier": "fast",
        "result": "outcome",
        "states": {
            "triage": {
                "structure": "One line naming the severity and why.",
                "prompt": (
                    "Assess the severity of this incident for a payments API.\n"
                    "Incident: intermittent 500s on the refund endpoint, ~2% of calls, "
                    "no data loss observed, a retry usually succeeds."
                ),
                "output": "assessment",
                "gates": [
                    {
                        "when": "the incident is severe enough to page a human on-call",
                        "escalate": True,
                        "to": "human",
                    },
                    {"when": "otherwise", "then": "ok", "to": "auto"},
                ],
            },
            "auto": {
                "structure": 'The word "AUTO_HANDLED".',
                "prompt": "Reply with exactly AUTO_HANDLED",
                "output": "outcome",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "human": {
                "structure": 'The word "ESCALATED".',
                "prompt": "Reply with exactly ESCALATED",
                "output": "outcome",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
        },
    },
    # 4) Self-correction gate: a `repair` loop on "grounded in the given fact"
    # stresses whether judges agree an answer is adequately grounded.
    "grounding_repair": {
        "machine": "grounding_repair",
        "entry": "answer",
        "budget": 6,
        "default_tier": "fast",
        "result": "final",
        "context": {"fact": "The store's return window is 30 days from delivery."},
        "states": {
            "answer": {
                "structure": "A one-sentence customer reply.",
                "prompt": (
                    "Answer the customer using ONLY this fact: {{fact}}\n"
                    "Customer: How long do I have to return an item?"
                ),
                "output": "final",
                "gates": [
                    {
                        "when": "the reply is grounded in the given fact and states 30 days",
                        "then": "ok",
                        "to": "END",
                    },
                    {
                        "when": "the reply is vague or not grounded in the fact",
                        "repair": 1,
                        "to": "answer",
                    },
                    {"when": "otherwise", "then": "ok", "to": "END"},
                ],
            },
        },
    },
}

# Back-compat alias for anything importing the original single machine.
MACHINE = MACHINES["gate_divergence"]


def _trace_signature(trace: list[dict]) -> str:
    """Compact, comparable signature of routing decisions (not full outputs)."""
    parts = []
    for step in trace:
        parts.append(
            f"{step.get('state')}|{step.get('gate')}|{step.get('gate_via')}|{step.get('to')}"
        )
    return " || ".join(parts)


def _output_hash(trace: list[dict]) -> str:
    blob = json.dumps([s.get("output") for s in trace], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def _run_once(
    provider_name: str,
    config: str,
    judge_tier: str | None = None,
    machine_doc: dict | None = None,
    build_llm=_build_llm,
) -> dict:
    """Run one machine once for one provider. `build_llm` is injectable so the
    offline suite can drive the harness with a scripted LLM (no keys)."""
    prov = load_provider(config, provider_name)
    # The missing-key skip only applies to the real live path; an injected
    # build_llm means there is no live call to gate (offline tests).
    if build_llm is _build_llm and not prov.api_key and prov.name != "local":
        return {"provider": provider_name, "skipped": True, "reason": "no API key"}
    doc = machine_doc if machine_doc is not None else MACHINE
    m = parse_machine(doc)
    # Default: judging follows each state's tier (SPEC §2.1). `--judge-tier` forces a
    # single tier's model for all gates, so pre/post-F1 divergence runs are comparable.
    judge_override = prov.tiers[judge_tier] if judge_tier else prov.judge_override()
    r = run(
        m,
        dict(m.context),
        {m.name: m},
        build_llm(prov),
        prov.tiers,
        judge_override,
        tier_params=prov.params,
        cost_budget=20_000,
    )
    return {
        "provider": provider_name,
        "machine": m.name,
        "skipped": False,
        "status": r.status,
        "error": r.error,
        "judge_tier": judge_tier,
        "judge_override": judge_override,
        "signature": _trace_signature(r.trace) if r.trace else "",
        "output_hash": _output_hash(r.trace) if r.trace else "",
        "gates": [
            {
                "state": s.get("state"),
                "gate": s.get("gate"),
                "gate_via": s.get("gate_via"),
                "judge_model": s.get("judge_model"),
                "to": s.get("to"),
                "judge_fallback": s.get("judge_fallback"),
            }
            for s in (r.trace or [])
        ],
        "usage": r.usage,
    }


def _pairwise_agreement(rows: list[dict]) -> list[dict]:
    """Pairwise signature agreement, computed WITHIN each machine — cross-machine
    signatures differ by construction, so pooling them would be meaningless."""
    ok = [r for r in rows if not r.get("skipped") and r.get("status") == "done"]
    out = []
    machines = sorted({r.get("machine") for r in ok}, key=lambda x: (x is None, x))
    for machine in machines:
        group = [r for r in ok if r.get("machine") == machine]
        for a, b in combinations(group, 2):
            pair = {
                "a": a["provider"],
                "b": b["provider"],
                "same_signature": a["signature"] == b["signature"],
                "same_outputs": a["output_hash"] == b["output_hash"],
            }
            if machine is not None:
                pair["machine"] = machine
            out.append(pair)
    return out


def _machine_rates(rows: list[dict]) -> dict[str, dict]:
    """Per-machine agreement rate + distinct signatures over the done rows."""
    done = [r for r in rows if not r.get("skipped") and r.get("status") == "done"]
    per: dict[str, dict] = {}
    for machine in sorted({r.get("machine") for r in done}, key=lambda x: (x is None, x)):
        group = [r for r in done if r.get("machine") == machine]
        pairs = _pairwise_agreement(group)
        agree = sum(1 for pair in pairs if pair["same_signature"])
        per[machine or "default"] = {
            "runs_done": len(group),
            "pairs": len(pairs),
            "signature_agreement_rate": (agree / len(pairs)) if pairs else None,
            "distinct_signatures": sorted({r["signature"] for r in group}),
        }
    return per


def _summary(rows: list[dict], names: list[str]) -> dict:
    pairs = _pairwise_agreement(rows)
    done = [r for r in rows if not r.get("skipped") and r.get("status") == "done"]
    agree = sum(1 for pair in pairs if pair["same_signature"])
    per_machine = _machine_rates(rows)
    return {
        "providers_attempted": names,
        "machines": sorted({r.get("machine") for r in done if r.get("machine")}),
        "runs_done": len(done),
        "runs_skipped": sum(1 for r in rows if r.get("skipped")),
        "runs_failed": sum(1 for r in rows if not r.get("skipped") and r.get("status") != "done"),
        "pairwise": pairs,
        # Pooled over all within-machine pairs; identical to the per-machine rate
        # for a single machine, so the release gate keeps one comparable number.
        "signature_agreement_rate": (agree / len(pairs)) if pairs else None,
        "per_machine": per_machine,
        "distinct_signatures": sorted({r["signature"] for r in done}),
    }


def _ci_errors(
    rows: list[dict], required: list[str], repeats: int, min_agreement: float | None
) -> list[str]:
    """Return release-gate failures without hiding unavailable or failed providers.

    With `repeats` runs per (provider, machine), a required provider must have
    `repeats * n_machines` successful rows; the agreement floor is enforced
    per-machine so no single machine can hide behind a high pooled average."""
    errors: list[str] = []
    # Count only machines that actually ran. Skipped-provider rows carry no
    # `machine` field (see `_run_once`), so a naive distinct-count over all rows
    # would include `None` and inflate `repeats * n_machines` — failing the
    # release gate even with perfect agreement whenever any optional provider
    # lacks a key (the normal release-matrix state).
    machines = {r.get("machine") for r in rows if r.get("machine") is not None}
    expected = repeats * max(1, len(machines))
    for name in required:
        provider_rows = [r for r in rows if r.get("provider") == name]
        if len(provider_rows) != expected:
            errors.append(
                f"required provider {name!r}: expected {expected} runs, got {len(provider_rows)}"
            )
            continue
        skipped = [r for r in provider_rows if r.get("skipped")]
        failed = [r for r in provider_rows if not r.get("skipped") and r.get("status") != "done"]
        if skipped:
            errors.append(f"required provider {name!r}: {len(skipped)} run(s) skipped")
        if failed:
            errors.append(f"required provider {name!r}: {len(failed)} run(s) failed")

    if min_agreement is None:
        return errors
    agreement_rows = [r for r in rows if not required or r.get("provider") in required]
    for machine, stats in _machine_rates(agreement_rows).items():
        rate = stats["signature_agreement_rate"]
        if rate is None or rate < min_agreement:
            label = "" if machine == "default" else f" [{machine}]"
            errors.append(
                f"signature agreement {rate!r}{label} is below required {min_agreement:.3f}"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="runtime YAML (default: config/runtime.example.yaml)",
    )
    p.add_argument(
        "--providers",
        default="deepseek,openai,anthropic,google,xai,mistral,openrouter",
        help="comma-separated provider names to try",
    )
    p.add_argument("--repeats", type=int, default=1, help="runs per provider")
    p.add_argument("--jsonl", type=Path, default=None, help="append raw rows here")
    p.add_argument("--summary-json", type=Path, default=None, help="write the summary JSON here")
    p.add_argument(
        "--require-providers",
        default="",
        help="comma-separated providers whose every repeat must finish successfully",
    )
    p.add_argument(
        "--min-agreement",
        type=float,
        default=None,
        help="minimum pairwise signature agreement in [0, 1] (release gate)",
    )
    p.add_argument(
        "--judge-tier",
        choices=("fast", "balanced", "reasoning"),
        default=None,
        help="force all gate judging onto this tier's model (default: follow each "
        "state's tier, SPEC §2.1). The demo machines are fast-tier throughout.",
    )
    p.add_argument(
        "--machines",
        default="gate_divergence",
        help="comma-separated machine names from the suite, or 'all'. Default is "
        f"the single 'gate_divergence' machine (release-gate compatible). "
        f"Available: {', '.join(MACHINES)}.",
    )
    args = p.parse_args(argv)

    if args.repeats < 1:
        p.error("--repeats must be at least 1")
    if args.min_agreement is not None and not 0 <= args.min_agreement <= 1:
        p.error("--min-agreement must be between 0 and 1")

    if args.machines.strip() == "all":
        machine_names = list(MACHINES)
    else:
        machine_names = [x.strip() for x in args.machines.split(",") if x.strip()]
    unknown_machines = sorted(set(machine_names) - set(MACHINES))
    if unknown_machines:
        p.error(f"unknown machines: {', '.join(unknown_machines)} (have: {', '.join(MACHINES)})")
    if not machine_names:
        p.error("--machines selected nothing")

    names = [x.strip() for x in args.providers.split(",") if x.strip()]
    required = [x.strip() for x in args.require_providers.split(",") if x.strip()]
    unknown_required = sorted(set(required) - set(names))
    if unknown_required:
        p.error(f"required providers not present in --providers: {', '.join(unknown_required)}")
    rows: list[dict] = []
    for machine_name in machine_names:
        doc = MACHINES[machine_name]
        for name in names:
            for i in range(args.repeats):
                try:
                    row = _run_once(name, args.config, judge_tier=args.judge_tier, machine_doc=doc)
                except Exception as e:  # provider/network/runtime failures become error rows
                    row = {
                        "provider": name,
                        "machine": machine_name,
                        "skipped": False,
                        "status": "error",
                        "error": f"{type(e).__name__}: {e}",
                    }
                row["repeat"] = i
                rows.append(row)
                tag = f"{machine_name}/{name}[{i}]"
                if row.get("skipped"):
                    print(f"# skip {tag}: {row.get('reason')}", file=sys.stderr)
                elif row.get("status") != "done":
                    print(f"# error {tag}: {row.get('error')}", file=sys.stderr)
                else:
                    print(
                        f"{tag}: status={row['status']} sig={row['signature']!r}", file=sys.stderr
                    )
                if args.jsonl:
                    with args.jsonl.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = _summary(rows, names)
    errors = _ci_errors(rows, required, args.repeats, args.min_agreement)
    summary["gate_errors"] = errors
    rendered = json.dumps(summary, indent=2, ensure_ascii=False)
    print(rendered)
    if args.summary_json:
        args.summary_json.write_text(rendered + "\n", encoding="utf-8")
    for error in errors:
        print(f"# release gate: {error}", file=sys.stderr)
    if errors:
        return 1
    done = [r for r in rows if not r.get("skipped") and r.get("status") == "done"]
    if len(done) < 2:
        print(
            "# need at least two successful providers to measure agreement",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
