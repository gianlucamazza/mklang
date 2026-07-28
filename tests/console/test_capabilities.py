"""Capability scope, tool metadata and audit redaction tests."""

import json

from mklang.console.capabilities import TOOL_METADATA, capability_key, metadata_for, redact
from mklang.controlflow import is_effectful
from mklang.tool_obs import tool_obs


def test_capabilities_are_scoped_and_unknown_tools_fail_closed():
    assert capability_key("approve", "send_reply") == "approve:send_reply"
    assert metadata_for("send_reply").irreversible is True
    unknown = metadata_for("third_party_tool")
    assert unknown.irreversible is True
    assert unknown.sensitivity == "unknown"


def test_read_only_agrees_with_the_engine_effect_class():
    """One source of truth for "can this tool change the world" (ADR 0030): the
    console's host policy derives `read_only`, it does not restate it."""
    for name, meta in TOOL_METADATA.items():
        assert meta.read_only is not is_effectful(name), name
    assert metadata_for("third_party_tool").read_only is False  # unclassified → effectful


def test_audit_redaction_preserves_shape_without_secrets():
    value = redact(
        {
            "token": "sk-secret-value",
            "note": "Authorization: Bearer abc123",
            "gh": "ghp_123456789012345",
        }
    )
    assert value["token"] == "[REDACTED]"
    assert "abc123" not in value["note"]
    assert "123456789012345" not in value["gh"]


def test_tool_observation_declares_status_retry_and_untrusted_data():
    payload = json.loads(tool_obs("search", stub=False, error="temporarily unavailable"))
    assert payload["status"] == "error"
    assert payload["retryable"] is False
    assert payload["untrusted"] is True
