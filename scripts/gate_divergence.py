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


def _run_once(provider_name: str, config: str) -> dict:
    prov = load_provider(config, provider_name)
    if not prov.api_key and prov.name != "local":
        return {"provider": provider_name, "skipped": True, "reason": "no API key"}
    m = parse_machine(MACHINE)
    r = run(
        m,
        dict(m.context),
        {m.name: m},
        _build_llm(prov),
        prov.tiers,
        prov.judge_model(),
        tier_params=prov.params,
        cost_budget=20_000,
    )
    return {
        "provider": provider_name,
        "skipped": False,
        "status": r.status,
        "error": r.error,
        "signature": _trace_signature(r.trace) if r.trace else "",
        "output_hash": _output_hash(r.trace) if r.trace else "",
        "gates": [
            {
                "state": s.get("state"),
                "gate": s.get("gate"),
                "gate_via": s.get("gate_via"),
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
    args = p.parse_args(argv)

    names = [x.strip() for x in args.providers.split(",") if x.strip()]
    rows: list[dict] = []
    for name in names:
        for i in range(args.repeats):
            try:
                row = _run_once(name, args.config)
            except Exception as e:  # noqa: BLE001
                row = {"provider": name, "skipped": True, "reason": str(e)}
            row["repeat"] = i
            rows.append(row)
            if row.get("skipped"):
                print(f"# skip {name}: {row.get('reason')}", file=sys.stderr)
            else:
                print(
                    f"{name}[{i}]: status={row['status']} sig={row['signature']!r}",
                    file=sys.stderr,
                )
            if args.jsonl:
                with args.jsonl.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    pairs = _pairwise_agreement(rows)
    done = [r for r in rows if not r.get("skipped") and r.get("status") == "done"]
    agree = sum(1 for pr in pairs if pr["same_signature"])
    summary = {
        "providers_attempted": names,
        "runs_done": len(done),
        "pairwise": pairs,
        "signature_agreement_rate": (agree / len(pairs)) if pairs else None,
        "distinct_signatures": sorted({r["signature"] for r in done}),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if len(done) < 2:
        print(
            "# need at least two successful providers to measure agreement",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
