"""Web search tool (ADR 0016): stub default, fake/tavily backends, structured obs."""

import io
import json
from urllib.error import URLError

from mklang.search import (
    FakeSearchBackend,
    SEARCH_SNIPPET_CHARS,
    SEARCH_URL_CHARS,
    TavilySearchBackend,
    configure_search,
    search,
    stub_search,
)
from mklang.tools import BUILTINS, load_tool_registry


def setup_function(_fn):
    configure_search(None)


def teardown_function(_fn):
    configure_search(None)


def test_stub_is_structured_and_honest(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("MKLANG_SEARCH_BACKEND", raising=False)
    raw = search({"query": "quantum"})
    data = json.loads(raw)
    assert data["tool"] == "search"
    assert data["stub"] is True
    assert data["query"] == "quantum"
    assert data["results"] == []
    assert "no external search bound" in data["error"]
    assert "TAVILY_API_KEY" in data["error"]
    assert "no external search bound" in data["message"]


def test_tavily_key_alone_auto_selects_backend(monkeypatch):
    """A present TAVILY_API_KEY opts the host into search without an extra flag."""
    monkeypatch.delenv("MKLANG_SEARCH_BACKEND", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    configure_search(None)

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"results": [{"title": "T", "url": "https://t.example", "content": "hit"}]}
            ).encode()

    # Patch the class used when auto-binding so we never hit the network.
    monkeypatch.setattr(
        "mklang.search.TavilySearchBackend",
        lambda key: FakeSearchBackend(
            [{"title": "Auto", "url": "https://a.example", "snippet": "ok"}]
        ),
    )
    data = json.loads(search({"query": "trump news"}))
    assert data["error"] is None
    assert data["stub"] is True  # FakeSearchBackend stand-in, not live Tavily
    assert data["results"] and data["results"][0]["title"] == "Auto"


def test_empty_query():
    data = json.loads(search({}))
    assert data["error"] == "empty query"
    assert data["stub"] is True
    assert data["tool"] == "search"


def test_fake_backend_via_configure():
    configure_search(FakeSearchBackend())
    data = json.loads(search({"query": "mklang", "max_results": 1}))
    assert data["error"] is None
    assert data["stub"] is True
    assert len(data["results"]) == 1
    assert "mklang" in data["results"][0]["snippet"]
    assert data["results"][0]["url"].startswith("https://")


def test_search_preserves_published_date_and_accepts_recency_inputs():
    configure_search(
        FakeSearchBackend(
            [
                {
                    "title": "Fresh",
                    "url": "https://example.com/2026",
                    "snippet": "hit",
                    "published_date": "2026-07-01",
                }
            ]
        )
    )
    data = json.loads(search({"query": "news", "max_results": 3, "days": 30, "topic": "news"}))
    assert data["error"] is None
    assert data["results"][0]["published_date"] == "2026-07-01"


def test_search_bounds_accumulated_observation_fields():
    configure_search(FakeSearchBackend([{"title": "T", "url": "u" * 1000, "snippet": "s" * 2000}]))
    data = json.loads(search({"query": "q"}))
    assert len(data["results"][0]["url"]) == SEARCH_URL_CHARS
    assert len(data["results"][0]["snippet"]) == SEARCH_SNIPPET_CHARS
    assert data["results"][0]["snippet"].endswith("…[truncated]")


def test_tavily_payload_includes_days_and_topic():
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {
                    "results": [
                        {
                            "title": "T",
                            "url": "https://t.example",
                            "content": "body",
                            "published_date": "2026-06-01",
                        }
                    ]
                }
            ).encode()

    def opener(req, timeout=0):
        captured["body"] = json.loads(req.data.decode())
        return _Resp()

    backend = TavilySearchBackend("tvly-test", opener=opener)
    rows = backend.search("q", max_results=2, days=14, topic="news")
    assert captured["body"]["days"] == 14
    assert captured["body"]["topic"] == "news"
    assert rows[0]["published_date"] == "2026-06-01"


def test_tavily_backend_uses_injected_opener():
    payload = json.dumps(
        {
            "results": [
                {"title": "A", "url": "https://a.example", "content": "snippet A"},
                {"title": "B", "url": "https://b.example", "content": "snippet B"},
            ]
        }
    ).encode()

    def opener(req, timeout=15):
        assert req.get_method() == "POST"
        return io.BytesIO(payload)

    # BytesIO lacks context manager protocol used by `with open_fn(...)`.
    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener_cm(req, timeout=15):
        return _Resp(payload)

    backend = TavilySearchBackend("k", opener=opener_cm)
    rows = backend.search("q", max_results=2)
    assert len(rows) == 2 and rows[0]["title"] == "A"


def test_search_surfaces_backend_errors():
    class Boom:
        def search(self, query, max_results=5):
            raise URLError("network down")

    configure_search(Boom())
    data = json.loads(search({"query": "x"}))
    assert data["results"] == []
    assert "search failed" in data["error"]


def test_builtin_registry_points_at_search(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("MKLANG_SEARCH_BACKEND", raising=False)
    configure_search(None)
    assert "search" in BUILTINS
    reg = load_tool_registry(include_entry_points=False)
    out = reg["search"]({"query": "y"})
    assert "no external search bound" in out


def test_stub_search_direct():
    data = json.loads(stub_search({"query": "z"}))
    assert data["tool"] == "search"
    assert data["stub"] is True
    assert "no external search bound" in data["error"]
