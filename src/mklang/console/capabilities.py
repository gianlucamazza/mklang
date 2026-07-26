"""Host-side capability and privacy policy for agent tool execution.

Capabilities deliberately live outside the ``.mkl`` language.  A machine can
declare that it needs a tool, but only the host can grant that tool for a
specific machine and execution surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


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


TOOL_METADATA: dict[str, ToolMetadata] = {
    "calc": ToolMetadata("calc"),
    "search": ToolMetadata("search", external_egress=True, sensitivity="external"),
    "search_kb": ToolMetadata("search_kb", external_egress=True),
    "send_reply": ToolMetadata(
        "send_reply", read_only=False, external_egress=True, irreversible=True, sensitivity="high"
    ),
    "list_files": ToolMetadata("list_files"),
    "read_file": ToolMetadata("read_file", sensitivity="workspace"),
    "write_file": ToolMetadata(
        "write_file", read_only=False, irreversible=False, sensitivity="workspace"
    ),
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
    """Return conservative metadata for unknown third-party tools."""
    return TOOL_METADATA.get(
        tool,
        ToolMetadata(
            tool,
            read_only=False,
            external_egress=True,
            irreversible=True,
            sensitivity="unknown",
            idempotent=False,
        ),
    )
