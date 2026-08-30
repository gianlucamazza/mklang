"""Shared metadata and validation helpers for Evidence Release rows."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0"
SPEC_VERSION = "0.4"


def runtime_version() -> str:
    try:
        return importlib.metadata.version("mklang")
    except importlib.metadata.PackageNotFoundError:
        return "1.3.1"


def started_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def provider_params(provider: object) -> dict[str, object]:
    """Return effective, non-secret provider parameters in stable JSON form."""
    params = getattr(provider, "params", {}) or {}
    return json.loads(json.dumps(params, sort_keys=True, default=str))


def envelope(
    *,
    experiment: str,
    provider: object,
    model: str,
    judge_model: str | None,
    judge_tier: str | None,
    params: dict[str, object] | None = None,
    **fields: object,
) -> dict[str, object]:
    row = {
        "schema_version": SCHEMA_VERSION,
        "runtime_version": runtime_version(),
        "spec_version": SPEC_VERSION,
        "experiment": experiment,
        "provider": provider.name if hasattr(provider, "name") else str(provider),
        "model": model,
        "started_at": fields.pop("started_at", started_at()),
        "judge_model": judge_model,
        "judge_tier": judge_tier,
        "provider_params": params or {},
        **fields,
    }
    return row


def sha256_json(value: object) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()
