"""Example machines: scenario coverage and the machines/ workspace mirror."""

from pathlib import Path

import pytest
import yaml

from mklang.loader import load_machine
from mklang.scripttest import match_expectation, run_scenario

EXAMPLES = Path("examples")
MACHINES = Path("machines")


@pytest.mark.parametrize("path", sorted(MACHINES.glob("*.mkl")), ids=lambda p: p.stem)
def test_machines_workspace_mirrors_examples(path):
    """Every workspace machine is a byte-identical copy of its examples/ twin.

    ``machines/`` is the canonical project workspace the console discovers
    (docs/guides/console.md); its files are demo copies of ``examples/`` and
    nothing pins the pair together but this test — same rationale as
    ``test_schema.test_schema_copies_are_byte_identical``.
    """
    twin = EXAMPLES / path.name
    assert twin.is_file(), f"{path} has no examples/ twin"
    assert path.read_bytes() == twin.read_bytes(), (
        f"{path} is out of sync with {twin}; re-sync from the source copy:\n    cp {twin} {path}"
    )


def _registry():
    machines = [load_machine(p) for p in sorted(EXAMPLES.glob("*.mkl"))]
    return {m.name: m for m in machines}


@pytest.mark.parametrize(
    "script",
    sorted(EXAMPLES.glob("*.test.yaml")),
    ids=lambda p: p.name.removesuffix(".test.yaml"),
)
def test_example_scenarios_pass(script):
    """Every examples/*.test.yaml scenario passes under the scripted harness."""
    machine = load_machine(script.with_name(script.name.removesuffix(".test.yaml") + ".mkl"))
    scenarios = yaml.safe_load(script.read_text(encoding="utf-8"))["scenarios"]
    assert scenarios, f"{script} declares no scenarios"
    registry = _registry()
    for sc in scenarios:
        result = run_scenario(machine, registry, sc)
        mismatches = match_expectation(result, sc["expect"])
        assert not mismatches, f"{script.name}::{sc['name']}: {mismatches[0]}"
