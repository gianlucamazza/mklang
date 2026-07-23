"""{{key.path}} interpolation and value formatting for prompts."""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Iterable
from typing import Any

_PAT = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

# Per-value cap when formatting into produce prompts (ADR 0017). High enough to
# be a no-op for normal machines; 0 disables. Hosts may override via render/fmt.
PROMPT_VALUE_CHARS = 20_000

# Untrusted-data fence grammar (SPEC §6): <data-NONCE>…</data-NONCE>. The prefix
# is normative and stable so tests and conformance cases can match on it; the
# nonce is fresh per LLM call so content cannot forge a closing tag.
DATA_FENCE_PREFIX = "<data-"


def mint_nonce(values: Iterable[str]) -> str:
    """A fresh fence nonce that appears in none of `values` (re-roll on collision).

    Collisions are astronomically unlikely; the re-roll exists so a value that
    embeds a previously leaked nonce (e.g. replayed from a trace) can never
    close its own fence."""
    while True:
        nonce = secrets.token_hex(6)
        if not any(nonce in v for v in values):
            return nonce


def wrap_data(text: str, nonce: str) -> str:
    """Fence one untrusted value byte-for-byte (no escaping, no mutation)."""
    return f"{DATA_FENCE_PREFIX}{nonce}>\n{text}\n</data-{nonce}>"


def lookup(ctx: dict, path: str) -> Any:
    """Resolve a dotted path into a nested dict; return None if missing."""
    cur = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _clip(text: str, max_chars: int) -> str:
    """Hard-cap a string; if truncated, end with an explicit marker inside the budget."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    marker = "…[truncated]"
    if len(marker) >= max_chars:
        return marker[:max_chars]
    return text[: max_chars - len(marker)] + marker


def fmt(value: object, *, max_chars: int | None = None) -> str:
    """Render a context value for inclusion in a prompt.

    Lists become a readable numbered enumeration (what a reducer wants to see).
    ``max_chars`` caps the formatted string (default ``PROMPT_VALUE_CHARS``;
    ``0`` = unlimited). Truncation is marked with ``…[truncated]`` (ADR 0017).
    """
    limit = PROMPT_VALUE_CHARS if max_chars is None else max_chars
    if value is None:
        return ""
    if isinstance(value, str):
        raw = value
    elif isinstance(value, list):
        # Nested items are not individually capped; the joined blob is.
        raw = "\n".join(f"{i + 1}. {fmt(x, max_chars=0)}" for i, x in enumerate(value))
    else:
        raw = json.dumps(value, ensure_ascii=False)
    return _clip(raw, limit)


def render(text: str | None, ctx: dict, *, value_chars: int | None = None) -> str:
    """Replace {{path}} occurrences in `text` with formatted context values.

    ``value_chars`` is the per-value cap passed to :func:`fmt` (None → default).
    """
    if text is None:
        return ""

    def rep(m: re.Match) -> str:
        v = lookup(ctx, m.group(1))
        return fmt(v, max_chars=value_chars) if v is not None else ""

    return _PAT.sub(rep, text)


def render_delimited(
    text: str | None, ctx: dict, *, value_chars: int | None = None, tainted: set[str] | None = None
) -> tuple[str, str | None]:
    """Like :func:`render`, but fence interpolations of tainted top-level keys.

    Returns ``(rendered, nonce)``; ``nonce`` is None when nothing was fenced
    (no tainted substitution), so callers add the untrusted-data system rule
    only when a fence is actually present. Trusted substitutions render bare —
    a machine whose prompt only interpolates author literals is byte-identical
    to plain :func:`render`.
    """
    if text is None:
        return "", None
    tainted = tainted or set()

    # Two passes: format every substitution first, then mint a nonce that
    # collides with none of the tainted payloads, then fence and substitute.
    pieces: list[tuple[str, bool]] = []  # (formatted value, is_tainted)
    for m in _PAT.finditer(text):
        v = lookup(ctx, m.group(1))
        formatted = fmt(v, max_chars=value_chars) if v is not None else ""
        pieces.append((formatted, m.group(1).split(".")[0] in tainted))
    if not any(t for _, t in pieces):
        return render(text, ctx, value_chars=value_chars), None
    nonce = mint_nonce(v for v, t in pieces if t)

    it = iter(pieces)

    def rep(_m: re.Match) -> str:
        formatted, is_tainted = next(it)
        return wrap_data(formatted, nonce) if is_tainted else formatted

    return _PAT.sub(rep, text), nonce


_WHOLE = re.compile(r"^\s*\{\{\s*([\w.]+)\s*\}\}\s*$")


def resolve(value: Any, ctx: dict) -> Any:
    """Resolve an `input:` map value (SPEC §4.8/§4.9, 0.3).

    A value that is exactly one `{{path}}` placeholder resolves to the RAW
    context value — lists and dicts cross the call/tool boundary intact. Any
    other string renders as prose; non-string YAML values pass through as-is."""
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    m = _WHOLE.match(value)
    if m:
        v = lookup(ctx, m.group(1))
        return "" if v is None else v
    return render(value, ctx)
