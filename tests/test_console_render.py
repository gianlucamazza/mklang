"""Unit tests for console conversation rendering (no Textual / no Pilot)."""

from io import StringIO

import pytest

pytest.importorskip("rich")

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.text import Text

from mklang.console import render as r


def _plain(renderable) -> str:
    buf = StringIO()
    Console(file=buf, force_terminal=False, width=80, color_system=None).print(renderable)
    return buf.getvalue()


def test_chrome_is_styled_text():
    out = r.chrome("[b]ok[/b]")
    assert isinstance(out, Text)
    assert "ok" in out.plain


def test_labeled_plain_does_not_interpret_body_markup():
    """Untrusted body with Rich-like tags stays literal (not bold)."""
    rendered = r.labeled_plain("[b]you:[/b] ", "array[0] and [b]injected[/b]")
    plain = rendered.plain
    assert "you:" in plain
    assert "array[0]" in plain
    assert "[b]injected[/b]" in plain
    # Body starts after the label; no style spans should cover the fake tag text.
    body_start = plain.index("array[0]")
    for span in rendered.spans:
        if span.start >= body_start:
            raise AssertionError(f"untrusted body must be unstyled, got {span}")


def test_labeled_markdown_renders_emphasis_not_rich_tags():
    body = "See **bold** and a [b]not-rich[/b] tag."
    rendered = r.labeled_markdown("[b green]agent:[/b green]", body)
    assert isinstance(rendered, Group)
    plain = _plain(rendered)
    assert "agent:" in plain
    assert "bold" in plain
    # Markdown leaves unknown [b]…[/b] as literal characters.
    assert "[b]not-rich[/b]" in plain or "not-rich" in plain
    # Emphasis should not leave the ** markers.
    assert "**bold**" not in plain


def test_fenced_json_is_code_block():
    payload = '{"status": "done", "x": [1]}'
    plain = _plain(r.fenced(payload, lang="json"))
    assert "status" in plain
    assert "done" in plain


def test_labeled_fenced_keeps_label_and_payload():
    payload = '{"status": "done"}'
    plain = _plain(r.labeled_fenced("[b green]result:[/b green]", payload, lang="json"))
    assert "result:" in plain
    assert "status" in plain


def test_bold_name_line_does_not_parse_name_as_markup():
    line = r.bold_name_line("weird[b]name", " · ok")
    assert line.plain.startswith("  weird[b]name")
    assert "ok" in line.plain


def test_fenced_returns_markdown_renderable():
    assert isinstance(r.fenced("hello"), Markdown)


def test_tree_turn_keeps_brackets_literal():
    label = r.tree_turn("see array[0] and [b]injected[/b]")
    assert isinstance(label, Text)
    assert "array[0]" in label.plain
    assert "[b]injected[/b]" in label.plain


def test_tree_run_has_no_expand_glyph():
    """Textual Tree owns ▶/▼ toggles; run labels must not add a second ▶."""
    label = r.tree_run("console_agent")
    assert label.plain == "console_agent"
    assert "▶" not in label.plain
    assert "▼" not in label.plain


def test_tree_preview_is_dim_plain_not_markup():
    label = r.tree_preview("**not md** and [b]x[/b]")
    assert "**not md**" in label.plain
    assert "[b]x[/b]" in label.plain


def test_tree_preview_truncates():
    long = "x" * 500
    label = r.tree_preview(long, limit=20)
    assert len(label.plain) == 20
    assert label.plain.endswith("…")


def test_tree_state_done_formats():
    with_to = r.tree_state_done("reply", "ok", "END")
    assert "reply" in with_to.plain and "→ END" in with_to.plain
    no_to = r.tree_state_done("halt", "fail", None)
    assert "(fail)" in no_to.plain
