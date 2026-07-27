"""Example payloads must validate against schema/run-result.schema.json (#71)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from mklang import host
from mklang.engine import RunResult

_SCHEMA_PATH = Path("schema/run-result.schema.json")


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(schema: dict, payload: dict) -> None:
    jsonschema.Draft7Validator(schema).validate(payload)


def test_schema_file_is_draft7(schema: dict) -> None:
    assert schema["$id"] == "https://mklang.dev/schema/run-result.schema.json"
    assert "status" in schema["properties"]


def test_build_output_done_validates(schema: dict) -> None:
    res = RunResult(
        status="done",
        trace=[{"step": 1, "state": "s1"}],
        context={},
        result="ok",
        usage={"input_tokens": 1, "output_tokens": 2},
    )
    _validate(schema, host.build_output(res))


def test_build_output_halt_validates(schema: dict) -> None:
    res = RunResult(
        status="halt",
        trace=[],
        context={},
        error="gate-fail",
        at="check",
        usage={"input_tokens": 0, "output_tokens": 0},
    )
    _validate(schema, host.build_output(res))


def test_build_output_suspended_validates(schema: dict) -> None:
    res = RunResult(
        status="suspended",
        trace=[],
        context={},
        error="escalated",
        at="review",
        usage=None,
    )
    out = host.build_output(res)
    out["checkpoint"] = "/tmp/ck.json"  # CLI surface extension
    _validate(schema, out)


def test_mcp_error_payload_validates(schema: dict) -> None:
    # MCP domain failures use status "error" (server.py); allowed by the schema.
    payload = {
        "status": "error",
        "error": "invalid-request",
        "result": None,
        "usage": None,
        "trace": [],
        "warnings": ["provide exactly one of source or path"],
    }
    _validate(schema, payload)


def test_done_with_non_null_error_fails(schema: dict) -> None:
    bad = {
        "status": "done",
        "error": "should-be-null",
        "result": "x",
        "usage": None,
        "trace": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, bad)
