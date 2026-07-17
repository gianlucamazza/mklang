"""Optional real web-search backends for the `search` host tool (ADR 0016).

Default remains offline: :func:`stub_search`. A process may bind a backend via
:func:`configure_search` / env ``MKLANG_SEARCH_BACKEND``. Observations are JSON
strings so tool states stay ``(dict) -> str``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Protocol

SearchFn = Callable[[dict], str]


class SearchBackend(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Return a list of {title, url, snippet} dicts (may be empty)."""
        ...


def _obs(query: str, results: list[dict], error: str | None = None) -> str:
    return json.dumps(
        {"query": query, "results": results, "error": error},
        ensure_ascii=False,
    )


def stub_search(inp: dict) -> str:
    """Offline default — honest no-op so demos never pretend they hit the web."""
    query = str(inp.get("query") or "").strip()
    return _obs(query, [], error="no external search bound")


class FakeSearchBackend:
    """Deterministic backend for tests and offline demos."""

    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or [
            {
                "title": "Example result",
                "url": "https://example.com/",
                "snippet": "A deterministic fake search hit for query testing.",
            }
        ]

    def search(self, query: str, max_results: int = 5) -> list[dict]:
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
        opener=None,
    ):
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout
        self._opener = opener  # injectable for tests: callable(Request, timeout) -> response

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        payload = json.dumps(
            {
                "api_key": self.api_key,
                "query": query,
                "max_results": max(1, min(int(max_results), 10)),
                "include_answer": False,
            }
        ).encode("utf-8")
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
            results.append(
                {
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "snippet": str(item.get("content") or item.get("snippet") or ""),
                }
            )
        return results


_backend: SearchBackend | None = None


def configure_search(backend: SearchBackend | None) -> None:
    """Bind (or clear) the process-wide search backend used by :func:`search`."""
    global _backend
    _backend = backend


def current_backend() -> SearchBackend | None:
    return _backend


def _backend_from_env() -> SearchBackend | None:
    """Lazy env binding: MKLANG_SEARCH_BACKEND=fake|tavily (default: none → stub)."""
    name = (os.environ.get("MKLANG_SEARCH_BACKEND") or "").strip().lower()
    if not name or name in ("stub", "none", "off"):
        return None
    if name == "fake":
        return FakeSearchBackend()
    if name == "tavily":
        key = os.environ.get("TAVILY_API_KEY") or ""
        if not key:
            return None  # fall through to stub with error in search()
        return TavilySearchBackend(key)
    return None


def search(inp: dict) -> str:
    """Host tool entry: stub unless a backend is configured (or env-selected)."""
    query = str(inp.get("query") or "").strip()
    if not query:
        return _obs("", [], error="empty query")
    try:
        max_results = int(inp.get("max_results") or 5)
    except (TypeError, ValueError):
        return _obs(query, [], error="max_results must be an integer")
    max_results = max(1, min(max_results, 10))

    backend = _backend if _backend is not None else _backend_from_env()
    if backend is None:
        # Keep the historical stub phrase discoverable for existing tests/docs,
        # while also emitting the structured observation contract.
        legacy = f"[no external search bound] query was: {query!r}"
        return json.dumps(
            {"query": query, "results": [], "error": "no external search bound", "message": legacy},
            ensure_ascii=False,
        )
    try:
        results = backend.search(query, max_results=max_results)
        if not isinstance(results, list):
            return _obs(query, [], error="backend returned non-list results")
        # Sanitize: only plain string fields, cap sizes (untrusted web — SPEC §11).
        clean = []
        for row in results[:max_results]:
            if not isinstance(row, dict):
                continue
            clean.append(
                {
                    "title": str(row.get("title") or "")[:300],
                    "url": str(row.get("url") or "")[:2000],
                    "snippet": str(row.get("snippet") or "")[:2000],
                }
            )
        return _obs(query, clean)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        return _obs(query, [], error=f"search failed: {e}")
    except Exception as e:  # never crash the machine on a tool boundary
        return _obs(query, [], error=f"search failed: {e}")
