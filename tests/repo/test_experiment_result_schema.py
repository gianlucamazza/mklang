"""Contract tests for reproducible experiment JSONL metadata rows."""

import json

from conftest import REPO_ROOT
from jsonschema import Draft7Validator


def _validator():
    schema = json.loads(
        (REPO_ROOT / "schema" / "experiment-result.schema.json").read_text(encoding="utf-8")
    )
    return Draft7Validator(schema)


def test_gate_row_matches_experiment_schema():
    row = {
        "experiment": "gate-divergence",
        "provider": "deepseek",
        "machine": "threshold_edge",
        "variant": "base",
        "repeat": 0,
        "status": "done",
        "input_hash": "a" * 64,
        "output_hash": "b" * 12,
        "route": "assess>within || within>END",
        "signature": "assess|0|llm|within",
    }
    assert list(_validator().iter_errors(row)) == []


def test_repair_row_requires_attempts():
    row = {
        "experiment": "repair-convergence",
        "provider": "deepseek",
        "machine": "std_refine",
        "item": "std-refine",
        "repeat": 0,
        "status": "done",
        "input_hash": "a" * 64,
        "attempts": [],
    }
    assert list(_validator().iter_errors(row)) == []


def test_schema_rejects_short_input_hash():
    row = {
        "experiment": "gate-divergence",
        "provider": "deepseek",
        "machine": "threshold_edge",
        "variant": "base",
        "repeat": 0,
        "status": "done",
        "input_hash": "short",
        "output_hash": "b" * 12,
        "route": "",
        "signature": "",
    }
    assert list(_validator().iter_errors(row))
