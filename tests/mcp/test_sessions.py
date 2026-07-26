"""The MCP session store (no `mcp` dependency needed)."""

from mklang.mcp.sessions import Session, SessionStore


def sess(**kw):
    base = dict(
        machine=None,
        registry={},
        llm=None,
        prov=None,
        tools={},
        hooks={},
        frames=[{"ctx": {}}],
        cost_budget=None,
        hitl=False,
        reason=None,
    )
    base.update(kw)
    return Session(**base)


def test_put_get_delete_roundtrip():
    store = SessionStore()
    h = store.put(sess(reason="escalated"))
    assert len(h) == 32  # opaque uuid4 hex
    assert store.get(h).reason == "escalated"
    store.delete(h)
    assert store.get(h) is None
    store.delete(h)  # idempotent


def test_handles_are_unique():
    store = SessionStore()
    assert store.put(sess()) != store.put(sess())


def test_fifo_eviction_cap():
    store = SessionStore(max_entries=2)
    h1, h2, h3 = (store.put(sess(reason=str(i))) for i in range(3))
    assert store.get(h1) is None  # oldest evicted
    assert store.get(h2).reason == "1"
    assert store.get(h3).reason == "2"
