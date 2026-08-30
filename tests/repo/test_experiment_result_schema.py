"""Contract tests for reproducible experiment JSONL metadata rows."""

import json

from conftest import REPO_ROOT
from jsonschema import Draft7Validator


def _validator():
    schema = json.loads(
        (REPO_ROOT / "schema" / "experiment-result.schema.json").read_text(encoding="utf-8")
    )
    return Draft7Validator(schema)


def _meta():
    return {
        "schema_version": "1.0",
        "runtime_version": "1.3.1",
        "spec_version": "0.4",
        "model": "fixture-model",
        "started_at": "2026-08-27T00:00:00Z",
        "judge_model": None,
        "judge_tier": None,
        "provider_params": {},
    }


def test_gate_row_matches_experiment_schema():
    row = {
        **_meta(),
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
        **_meta(),
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
        **_meta(),
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


def test_schema_rejects_unknown_stable_field():
    row = {
        **_meta(),
        "experiment": "gate-divergence",
        "provider": "x",
        "repeat": 0,
        "status": "done",
        "input_hash": "a" * 64,
        "unexpected": True,
    }
    assert list(_validator().iter_errors(row))
