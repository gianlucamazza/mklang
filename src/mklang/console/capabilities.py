"""Host-side capability and privacy policy for agent tool execution.

Capabilities deliberately live outside the ``.mkl`` language.  A machine can
declare that it needs a tool, but only the host can grant that tool for a
specific machine and execution surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..controlflow import is_effectful


@dataclass(frozen=True)
class ToolMetadata:
    name: str
    read_only: bool = True
    external_egress: bool = False
    irreversible: bool = False
    sensitivity: str = "normal"
    idempotent: bool = True

    @property
    def capability(self) -> str:
        return self.name


def _meta(name: str, **policy: Any) -> ToolMetadata:
    """Host policy for a tool, with `read_only` taken from the language's own
    effect classification (`controlflow.TOOL_EFFECTS`, ADR 0030).

    The question "can this tool change the world" is answered in exactly one
    place. The console adds what the engine has no opinion about — egress,
    reversibility, sensitivity — and never restates the effect class, which is
    how the two could have drifted apart."""
    return ToolMetadata(name, read_only=not is_effectful(name), **policy)


TOOL_METADATA: dict[str, ToolMetadata] = {
    "calc": _meta("calc"),
    "search": _meta("search", external_egress=True, sensitivity="external"),
    "search_kb": _meta("search_kb", external_egress=True),
    "send_reply": _meta("send_reply", external_egress=True, irreversible=True, sensitivity="high"),
    "list_files": _meta("list_files"),
    "read_file": _meta("read_file", sensitivity="workspace"),
    "write_file": _meta("write_file", irreversible=False, sensitivity="workspace"),
}


def capability_key(machine: str, tool: str) -> str:
    """Return the stable scoped grant key used by interactive surfaces."""
    return f"{machine}:{tool}"


_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(api[_-]?key|token|secret|password|authorization)(\s*[=:]\s*)[^\s,;]+(?:\s+[^\s,;]+)?"
    ),
    re.compile(r"\b(sk|ghp|github_pat|xoxb|xoxp)[_-][A-Za-z0-9_-]{12,}\b"),
)
_SENSITIVE_KEYS = {"api_key", "token", "secret", "password", "authorization", "content"}


def redact_text(value: str) -> str:
    """Redact common credential-shaped values before they enter audit output."""
    result = value
    for pattern in _SECRET_PATTERNS:

        def replacement(match: re.Match[str]) -> str:
            if match.lastindex and match.lastindex >= 2:
                return f"{match.group(1)}{match.group(2)}[REDACTED]"
            return "[REDACTED]"

        result = pattern.sub(replacement, result)
    return result


def redact(value: Any, *, key: str = "") -> Any:
    """Recursively redact sensitive audit fields while preserving useful shape."""
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]" if str(k).lower() in _SENSITIVE_KEYS else redact(v, key=str(k))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item, key=key) for item in value[:100]]
    if isinstance(value, str):
        return "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else redact_text(value[:2000])
    return value


def metadata_for(tool: str) -> ToolMetadata:
    """Return conservative metadata for unknown third-party tools.

    The unknown default agrees with the engine by construction: an unclassified
    tool is effectful there (ADR 0030) and not read-only here."""
    return TOOL_METADATA.get(
        tool,
        ToolMetadata(
            tool,
            read_only=not is_effectful(tool),
            external_egress=True,
            irreversible=True,
            sensitivity="unknown",
            idempotent=False,
        ),
    )
