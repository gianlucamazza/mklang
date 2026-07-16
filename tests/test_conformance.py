"""Reference runner for the conformance suite (conformance/README.md).

Any mklang implementation must pass these cases with its own runner; this one
binds them to the reference interpreter. All scripted-LLM / hook / tool / matcher
logic lives in `mklang.scripttest` — the single source of truth shared with the
`mklang test` CLI. This runner just loads each case and asserts the expectation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mklang.scripttest import build_registry, match_expectation, run_scenario

CASES = sorted(Path("conformance/cases").glob("*.yaml"))


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_conformance(path):
    case = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert case["case"] == path.stem, "case name must match the filename stem"
    machine, registry = build_registry(case)
    result = run_scenario(machine, registry, case)
    mismatches = match_expectation(result, case["expect"])
    assert not mismatches, (
        f"{path.stem}: " + "; ".join(str(m) for m in mismatches) + f"\ntrace={result.trace}"
    )
