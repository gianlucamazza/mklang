"""Shared observation envelope for host I/O tools (ADR 0020).

External / side-effect tools return a JSON string so machines and surfaces can
tell stub vs live honestly. Pure offline tools (e.g. ``calc``) need not use this.
"""

from __future__ import annotations

import json
from typing import Any


def tool_obs(
    tool: str,
    *,
    stub: bool,
    error: str | None = None,
    **payload: Any,
) -> str:
    """Build a structured tool observation string.

    Stable fields: ``tool``, ``stub``, ``error``. Extra keyword args become
    payload fields (e.g. ``results``, ``facts``, ``sent``).
    """
    body: dict[str, Any] = {"tool": tool, "stub": bool(stub), "error": error}
    body.update(payload)
    return json.dumps(body, ensure_ascii=False)
