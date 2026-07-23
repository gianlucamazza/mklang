"""Knowledge-base backends for the `search_kb` host tool (ADR 0020).

Default is an honest structured **stub** (demo policy facts, ``stub: true``).
Bind a fake or custom backend via :func:`configure_kb` / env
``MKLANG_KB_BACKEND=fake|stub``. Production hosts replace the tool via entry
points.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol

from .tool_obs import tool_obs

if TYPE_CHECKING:
    from .toolconfig import ToolsConfig

# Deterministic showcase facts (triage demos). Not a real KB.
_DEFAULT_FACTS = [
    "Warranty: 30-day return on unopened items with receipt.",
    "Billing: refunds over €50 require manager review.",
    "Bugs: known issue tracker acknowledges intermittent login 5xx; workaround is retry after 60s.",
]


class KBBackend(Protocol):
    def lookup(self, query: str) -> list[str]:
        """Return fact strings for the query (may be empty)."""
        ...


class StubKBBackend:
    """Default offline KB: fixed demo facts tagged with the query."""

    def lookup(self, query: str) -> list[str]:
        return list(_DEFAULT_FACTS) + [f"(stub demo facts for query={query!r})"]


class FakeKBBackend:
    """Deterministic custom facts for tests/demos (still stub: true)."""

    def __init__(self, facts: list[str] | None = None):
        self.facts = facts or [
            "Fake KB: product X is covered under plan Basic.",
            "Fake KB: contact support@example.com for escalations.",
        ]

    def lookup(self, query: str) -> list[str]:
        return [f"{f} (q={query!r})" for f in self.facts]


_backend: KBBackend | None = None


def configure_kb(backend: KBBackend | None) -> None:
    """Bind (or clear) the process-wide KB backend used by :func:`search_kb`."""
    global _backend
    _backend = backend


def current_kb_backend() -> KBBackend | None:
    return _backend


def resolve_backend_name(tc: "ToolsConfig | None" = None) -> tuple[str, str]:
    """Backend name + source layer: env > ``tools.kb.backend`` config > stub."""
    from .toolconfig import current_tools

    env = (os.environ.get("MKLANG_KB_BACKEND") or "").strip().lower()
    if env:
        return ("fake" if env == "fake" else "stub"), "env"
    tc = tc if tc is not None else current_tools()
    if tc.kb_backend:
        return ("fake" if tc.kb_backend.strip().lower() == "fake" else "stub"), "config"
    return "stub", "default"


def _backend_from_settings() -> KBBackend:
    name, _source = resolve_backend_name()
    if name == "fake":
        return FakeKBBackend()
    # stub / unknown → default stub
    return StubKBBackend()


def search_kb(inp: dict) -> str:
    """Host tool: structured KB lookup (stub/fake by default)."""
    query = str(inp.get("query") or inp.get("q") or "").strip()
    if not query:
        return tool_obs(
            "search_kb",
            stub=True,
            error="empty query",
            query="",
            facts=[],
            note="Host should bind a real RAG/KB tool for production.",
        )

    backend = _backend if _backend is not None else _backend_from_settings()
    try:
        # Widened to object: third-party backends may violate the protocol,
        # and the isinstance guard below is the boundary that catches it.
        facts: object = backend.lookup(query)
        if not isinstance(facts, list):
            return tool_obs(
                "search_kb",
                stub=True,
                error="backend returned non-list facts",
                query=query,
                facts=[],
            )
        clean = [str(f)[:2000] for f in facts if f is not None][:50]
        return tool_obs(
            "search_kb",
            stub=True,  # reference has no live KB; entry points replace the tool
            error=None,
            query=query,
            facts=clean,
            note="Host should bind a real RAG/KB tool for production.",
        )
    except Exception as e:  # never crash the machine on a tool boundary
        return tool_obs(
            "search_kb",
            stub=True,
            error=f"kb lookup failed: {e}",
            query=query,
            facts=[],
        )
