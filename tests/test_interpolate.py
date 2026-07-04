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
