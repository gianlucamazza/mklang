#!/usr/bin/env python3
"""How much of a machine corpus can act on a tainted decision? (ADR 0031 §1)

ADR 0030 defaults `on_untrusted_flow` to `report`. ADR 0031 §1 names the
condition that would flip it: **more than one in four effectful tool states**
across real machines reachable on a judge-made decision over external data,
plus author reports. The lint half has existed since 0.7 (`_flow_taint_findings`,
a `note:`); nothing counted. This counts.

Offline and deterministic: it walks `.mkl` files, asks the same static analysis
the lint runs, and reports

    incidence = flagged effectful tool states / all effectful tool states

per machine and pooled. No provider, no key, no cost — the number ADR 0031
wants is a property of the documents.

Usage:
    uv run python scripts/taint_incidence.py [DIR ...] [--json OUT]

With no DIR: the bundled stdlib + examples/ — our own corpus, which is a floor,
not the population ADR 0031 §1 is really about (machines outside this repo).
A dated row belongs in docs/experiments/ either way; the external corpus can
reuse this tool unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mklang.controlflow import is_effectful  # noqa: E402
from mklang.lint import _flow_taint_findings  # noqa: E402
from mklang.registry import load_registry  # noqa: E402


def corpus_dirs(argv_dirs: list[str]) -> list[Path]:
    if argv_dirs:
        return [Path(d) for d in argv_dirs]
    return [REPO / "src" / "mklang" / "data" / "stdlib", REPO / "examples"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dirs", nargs="*", help="machine directories (default: stdlib + examples)")
    parser.add_argument("--json", dest="json_out", help="write the summary JSON here")
    args = parser.parse_args()

    registry: dict = {}
    for directory in corpus_dirs(args.dirs):
        registry.update(load_registry(directory, validate=False))
    if not registry:
        print("no machines found", file=sys.stderr)
        return 2

    per_machine: dict[str, dict] = {}
    total_effectful = 0
    total_flagged = 0
    for name, machine in sorted(registry.items()):
        effectful = [
            sid
            for sid, state in machine.states.items()
            if state.kind == "tool" and is_effectful(state.tool)
        ]
        findings = _flow_taint_findings(machine, registry)
        flagged = [sid for sid in effectful if any(f.startswith(f"note: {sid}:") for f in findings)]
        per_machine[name] = {
            "effectful_tool_states": len(effectful),
            "flagged": len(flagged),
            "flagged_states": flagged,
        }
        total_effectful += len(effectful)
        total_flagged += len(flagged)

    incidence = (total_flagged / total_effectful) if total_effectful else None
    summary = {
        "machines": len(registry),
        "effectful_tool_states": total_effectful,
        "flagged": total_flagged,
        "incidence": incidence,
        "threshold_adr_0031": 0.25,
        "per_machine": {k: v for k, v in per_machine.items() if v["effectful_tool_states"]},
    }
    print(json.dumps(summary, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
