"""Optional real web-search backends for the `search` host tool (ADR 0016 / 0020).

Default remains offline: structured stub with ``stub: true``. Bind a real
backend via :func:`configure_search` / env ``MKLANG_SEARCH_BACKEND``.
Observations are JSON strings so tool states stay ``(dict) -> str``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from .tool_obs import tool_obs

if TYPE_CHECKING:
    from .toolconfig import ToolsConfig

SearchFn = Callable[[dict], str]

# Search observations are often accumulated across multiple queries and then
# interpolated into a single model prompt. Keep each hit useful without letting
# the second query batch consume the whole prompt-side working-memory cap.
SEARCH_SNIPPET_CHARS = 800
SEARCH_URL_CHARS = 500


def _clip_observation_field(value: object, limit: int) -> str:
    text = str(value or "")
    marker = "…[truncated]"
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(marker))] + marker


class SearchBackend(Protocol):
    def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        days: int | None = None,
        topic: str | None = None,
    ) -> list[dict]:
        """Return a list of {title, url, snippet, published_date?} dicts."""
        ...


def _obs(
    query: str,
    results: list[dict],
    error: str | None = None,
    *,
    stub: bool,
    **extra: object,
) -> str:
    return tool_obs(
        "search",
        stub=stub,
        error=error,
        query=query,
        results=results,
        **extra,
    )


def stub_search(inp: dict) -> str:
    """Offline default — honest no-op so demos never pretend they hit the web."""
    query = str(inp.get("query") or "").strip()
    if not query:
        return _obs("", [], error="empty query", stub=True)
    how = (
        "no external search bound — set TAVILY_API_KEY (auto-enables Tavily) "
        "or MKLANG_SEARCH_BACKEND=fake|tavily"
    )
    return _obs(
        query,
        [],
        error=how,
        stub=True,
        message=f"[no external search bound] query was: {query!r}",
    )


class FakeSearchBackend:
    """Deterministic backend for tests and offline demos (still ``stub: true``)."""

    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or [
            {
                "title": "Example result",
                "url": "https://example.com/",
                "snippet": "A deterministic fake search hit for query testing.",
            }
        ]

    def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        days: int | None = None,
        topic: str | None = None,
    ) -> list[dict]:
        del days, topic  # accepted for API parity; fake ignores filters
        out = []
        for row in self.rows[: max(0, max_results)]:
            item = dict(row)
            item["snippet"] = f"{item.get('snippet', '')} (q={query!r})".strip()
            out.append(item)
        return out


class TavilySearchBackend:
    """Tavily Search API (https://tavily.com) — requires TAVILY_API_KEY."""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://api.tavily.com/search",
        timeout: float = 15.0,
        opener: Callable[..., Any] | None = None,
    ):
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout
        self._opener = opener  # injectable for tests: callable(Request, timeout) -> response

    def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        days: int | None = None,
        topic: str | None = None,
    ) -> list[dict]:
        body_obj: dict = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max(1, min(int(max_results), 10)),
            "include_answer": False,
        }
        if days is not None:
            body_obj["days"] = max(1, min(int(days), 365))
        if topic:
            t = str(topic).strip().lower()
            if t in ("general", "news"):
                body_obj["topic"] = t
        payload = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        open_fn = self._opener or urllib.request.urlopen
        with open_fn(req, timeout=self.timeout) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        results = []
        for item in data.get("results") or []:
            row = {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("content") or item.get("snippet") or ""),
            }
            pub = item.get("published_date") or item.get("date")
            if pub:
                row["published_date"] = str(pub)[:64]
            results.append(row)
        return results


_backend: SearchBackend | None = None


def configure_search(backend: SearchBackend | None) -> None:
    """Bind (or clear) the process-wide search backend used by :func:`search`."""
    global _backend
    _backend = backend


def current_backend() -> SearchBackend | None:
    return _backend


def resolve_backend_name(tc: "ToolsConfig | None" = None) -> tuple[str, str]:
    """Resolve the backend name and its source layer (shared with doctor).

    Precedence (ADR 0016/0023): explicit ``MKLANG_SEARCH_BACKEND`` env >
    ``tools.search.backend`` config > default (auto-Tavily when
    ``TAVILY_API_KEY`` is present, else stub). ``none``/``off`` and unknown
    names degrade to ``stub`` like they always did.
    """
    from .toolconfig import current_tools

    env = (os.environ.get("MKLANG_SEARCH_BACKEND") or "").strip().lower()
    if env:
        return (env if env in ("fake", "tavily") else "stub"), "env"
    tc = tc if tc is not None else current_tools()
    if tc.search_backend:
        name = tc.search_backend.strip().lower()
        return (name if name in ("fake", "tavily") else "stub"), "config"
    if os.environ.get("TAVILY_API_KEY"):
        return "tavily", "default"
    return "stub", "default"


def _backend_from_settings() -> SearchBackend | None:
    """Lazy binding: build the resolved backend (env > config > default)."""
    name, _source = resolve_backend_name()
    if name == "fake":
        return FakeSearchBackend()
    if name == "tavily":
        key = os.environ.get("TAVILY_API_KEY") or ""
        return TavilySearchBackend(key) if key else None
    return None


def search(inp: dict) -> str:
    """Host tool entry: stub unless a backend is configured (or env-selected)."""
    query = str(inp.get("query") or "").strip()
    if not query:
        return _obs("", [], error="empty query", stub=True)
    try:
        max_results = int(inp.get("max_results") or 5)
    except (TypeError, ValueError):
        return _obs(query, [], error="max_results must be an integer", stub=True)
    max_results = max(1, min(max_results, 10))

    days: int | None = None
    if inp.get("days") not in (None, ""):
        try:
            days = int(inp["days"])
        except (TypeError, ValueError):
            return _obs(query, [], error="days must be an integer", stub=True)
    topic = str(inp.get("topic") or "").strip() or None

    backend = _backend if _backend is not None else _backend_from_settings()
    if backend is None:
        how = (
            "no external search bound — set TAVILY_API_KEY (auto-enables Tavily) "
            "or MKLANG_SEARCH_BACKEND=fake|tavily"
        )
        legacy = f"[no external search bound] query was: {query!r}"
        return _obs(query, [], error=how, stub=True, message=legacy)

    is_fake = isinstance(backend, FakeSearchBackend)
    try:
        # Widened to Any: third-party backends may violate the protocol, and
        # the isinstance guards below are the boundary that catches it.
        results: Any
        try:
            results = backend.search(query, max_results=max_results, days=days, topic=topic)
        except TypeError:
            results = backend.search(query, max_results=max_results)
        if not isinstance(results, list):
            return _obs(query, [], error="backend returned non-list results", stub=is_fake)
        clean = []
        for row in results[:max_results]:
            if not isinstance(row, dict):
                continue
            item = {
                "title": _clip_observation_field(row.get("title"), 300),
                "url": _clip_observation_field(row.get("url"), SEARCH_URL_CHARS),
                "snippet": _clip_observation_field(row.get("snippet"), SEARCH_SNIPPET_CHARS),
            }
            pub = row.get("published_date")
            if pub:
                item["published_date"] = str(pub)[:64]
            clean.append(item)
        # Fake is still not live web; live backends (Tavily) set stub=False.
        return _obs(query, clean, stub=is_fake)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        return _obs(query, [], error=f"search failed: {e}", stub=is_fake)
    except Exception as e:  # never crash the machine on a tool boundary
        return _obs(query, [], error=f"search failed: {e}", stub=is_fake)
