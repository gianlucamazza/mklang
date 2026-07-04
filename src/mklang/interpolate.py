"""{{key.path}} interpolation and value formatting for prompts."""

from __future__ import annotations

import json
import re

_PAT = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def lookup(ctx: dict, path: str):
    """Resolve a dotted path into a nested dict; return None if missing."""
    cur = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def fmt(value) -> str:
    """Render a context value for inclusion in a prompt.

    Lists become a readable numbered enumeration (what a reducer wants to see)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(f"{i + 1}. {fmt(x)}" for i, x in enumerate(value))
    return json.dumps(value, ensure_ascii=False)


def render(text: str | None, ctx: dict) -> str:
    """Replace {{path}} occurrences in `text` with formatted context values."""
    if text is None:
        return ""

    def rep(m: re.Match) -> str:
        v = lookup(ctx, m.group(1))
        return fmt(v) if v is not None else ""

    return _PAT.sub(rep, text)
