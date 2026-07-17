"""Web search tool (ADR 0016): stub default, fake/tavily backends, structured obs."""

import io
import json
from urllib.error import URLError

from mklang.search import (
    FakeSearchBackend,
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


def test_stub_is_structured_and_honest():
    raw = search({"query": "quantum"})
    data = json.loads(raw)
    assert data["query"] == "quantum"
    assert data["results"] == []
    assert "no external search bound" in data["error"]
    assert "no external search bound" in data["message"]


def test_empty_query():
    data = json.loads(search({}))
    assert data["error"] == "empty query"


def test_fake_backend_via_configure():
    configure_search(FakeSearchBackend())
    data = json.loads(search({"query": "mklang", "max_results": 1}))
    assert data["error"] is None
    assert len(data["results"]) == 1
    assert "mklang" in data["results"][0]["snippet"]
    assert data["results"][0]["url"].startswith("https://")


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


def test_builtin_registry_points_at_search():
    assert "search" in BUILTINS
    reg = load_tool_registry(include_entry_points=False)
    out = reg["search"]({"query": "y"})
    assert "no external search bound" in out


def test_stub_search_direct():
    data = json.loads(stub_search({"query": "z"}))
    assert data["error"] == "no external search bound"
