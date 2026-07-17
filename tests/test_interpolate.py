from mklang.interpolate import fmt, lookup, render


def test_render_nested():
    assert render("hi {{a.b}}", {"a": {"b": "x"}}) == "hi x"


def test_render_missing_is_empty():
    assert render("[{{nope}}]", {}) == "[]"


def test_fmt_list_is_numbered():
    assert fmt(["a", "b"]) == "1. a\n2. b"


def test_lookup_dotted():
    assert lookup({"a": {"b": 1}}, "a.b") == 1
    assert lookup({"a": {}}, "a.b.c") is None


def test_fmt_clips_large_values_with_marker():
    big = "x" * 100
    out = fmt(big, max_chars=30)
    assert out.endswith("…[truncated]")
    assert len(out) <= 30


def test_fmt_unlimited_when_max_chars_zero():
    big = "y" * 50_000
    assert fmt(big, max_chars=0) == big


def test_render_respects_value_chars():
    out = render("{{blob}}", {"blob": "z" * 100}, value_chars=25)
    assert "truncated" in out and len(out) <= 25
