#!/usr/bin/env python3
"""Measure cross-provider gate agreement on a fixed machine + inputs.

Syntactic portability ("same .mk, any provider") does not imply semantic
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mklang.cli import _build_llm  # noqa: E402
from mklang.config import load_provider  # noqa: E402
from mklang.engine import run  # noqa: E402
from mklang.model import parse_machine  # noqa: E402

DEFAULT_CONFIG = str(ROOT / "config" / "runtime.example.yaml")

# Fixed synthetic machine: produce a short label, then three prose routes.
# Designed so the judge has a non-trivial choice (not only `otherwise`).
MACHINE = {
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
}


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


def _run_once(provider_name: str, config: str, judge_tier: str | None = None) -> dict:
    prov = load_provider(config, provider_name)
    if not prov.api_key and prov.name != "local":
        return {"provider": provider_name, "skipped": True, "reason": "no API key"}
    m = parse_machine(MACHINE)
    # Default: judging follows each state's tier (SPEC §2.1). `--judge-tier` forces a
    # single tier's model for all gates, so pre/post-F1 divergence runs are comparable.
    judge_override = prov.tiers[judge_tier] if judge_tier else prov.judge_override()
    r = run(
        m,
        dict(m.context),
        {m.name: m},
        _build_llm(prov),
        prov.tiers,
        judge_override,
        tier_params=prov.params,
        cost_budget=20_000,
    )
    return {
        "provider": provider_name,
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
    ok = [r for r in rows if not r.get("skipped") and r.get("status") == "done"]
    out = []
    for a, b in combinations(ok, 2):
        out.append(
            {
                "a": a["provider"],
                "b": b["provider"],
                "same_signature": a["signature"] == b["signature"],
                "same_outputs": a["output_hash"] == b["output_hash"],
            }
        )
    return out


def _summary(rows: list[dict], names: list[str]) -> dict:
    pairs = _pairwise_agreement(rows)
    done = [r for r in rows if not r.get("skipped") and r.get("status") == "done"]
    agree = sum(1 for pair in pairs if pair["same_signature"])
    return {
        "providers_attempted": names,
        "runs_done": len(done),
        "runs_skipped": sum(1 for r in rows if r.get("skipped")),
        "runs_failed": sum(1 for r in rows if not r.get("skipped") and r.get("status") != "done"),
        "pairwise": pairs,
        "signature_agreement_rate": (agree / len(pairs)) if pairs else None,
        "distinct_signatures": sorted({r["signature"] for r in done}),
    }


def _ci_errors(
    rows: list[dict], required: list[str], repeats: int, min_agreement: float | None
) -> list[str]:
    """Return release-gate failures without hiding unavailable or failed providers."""
    errors: list[str] = []
    for name in required:
        provider_rows = [r for r in rows if r.get("provider") == name]
        if len(provider_rows) != repeats:
            errors.append(
                f"required provider {name!r}: expected {repeats} runs, got {len(provider_rows)}"
            )
            continue
        skipped = [r for r in provider_rows if r.get("skipped")]
        failed = [r for r in provider_rows if not r.get("skipped") and r.get("status") != "done"]
        if skipped:
            errors.append(f"required provider {name!r}: {len(skipped)} run(s) skipped")
        if failed:
            errors.append(f"required provider {name!r}: {len(failed)} run(s) failed")

    agreement_rows = [r for r in rows if not required or r.get("provider") in required]
    summary = _summary(
        agreement_rows, required or sorted({r.get("provider", "") for r in agreement_rows})
    )
    agreement = summary["signature_agreement_rate"]
    if min_agreement is not None and (agreement is None or agreement < min_agreement):
        errors.append(f"signature agreement {agreement!r} is below required {min_agreement:.3f}")
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
        "state's tier, SPEC §2.1). The demo machine is fast-tier throughout.",
    )
    args = p.parse_args(argv)

    if args.repeats < 1:
        p.error("--repeats must be at least 1")
    if args.min_agreement is not None and not 0 <= args.min_agreement <= 1:
        p.error("--min-agreement must be between 0 and 1")

    names = [x.strip() for x in args.providers.split(",") if x.strip()]
    required = [x.strip() for x in args.require_providers.split(",") if x.strip()]
    unknown_required = sorted(set(required) - set(names))
    if unknown_required:
        p.error(f"required providers not present in --providers: {', '.join(unknown_required)}")
    rows: list[dict] = []
    for name in names:
        for i in range(args.repeats):
            try:
                row = _run_once(name, args.config, judge_tier=args.judge_tier)
            except Exception as e:  # noqa: BLE001
                row = {
                    "provider": name,
                    "skipped": False,
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                }
            row["repeat"] = i
            rows.append(row)
            if row.get("skipped"):
                print(f"# skip {name}: {row.get('reason')}", file=sys.stderr)
            elif row.get("status") != "done":
                print(f"# error {name}: {row.get('error')}", file=sys.stderr)
            else:
                print(
                    f"{name}[{i}]: status={row['status']} sig={row['signature']!r}",
                    file=sys.stderr,
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
