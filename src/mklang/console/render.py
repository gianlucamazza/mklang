"""Safe rendering helpers for the console TUI (conversation log + activity tree).

Separates UI chrome (fixed styles) from untrusted content (user input, LLM
prose, tool observations, event previews). Agent replies render as CommonMark;
tree labels and user text stay plain ``Text`` segments so ``[brackets]`` never
inject Rich markup tags.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.text import Text

CODE_THEME = "monokai"
PREVIEW_MAX = 200  # align with engine._preview default for event output

STATUS_GLYPHS = {
    "ready": "●",
    "running": "◐",
    "waiting": "⏸",
    "stopping": "■",
    "error": "!",
}


def chrome(markup: str) -> Text:
    """Internal-only Rich markup — never interpolate untrusted strings."""
    return Text.from_markup(markup)


def labeled_plain(label_markup: str, body: str) -> Text:
    """Chrome label + plain body (no markup interpretation of body)."""
    return Text.from_markup(label_markup) + Text(body or "")


def bold_name_line(name: str, suffix: str = "") -> Text:
    """Bold name (plain, not markup) + plain suffix — for catalog rows."""
    line = Text("  ")
    line.append(name or "", style="bold")
    if suffix:
        line.append(suffix)
    return line


def labeled_markdown(label_markup: str, body: str) -> RenderableType:
    """Chrome label, then CommonMark body (agent prose)."""
    return Group(
        Text.from_markup(label_markup),
        Markdown(body or "", code_theme=CODE_THEME, hyperlinks=True),
    )


def fenced(body: str, lang: str = "") -> RenderableType:
    """Opaque text as a fenced code block (JSON verdicts, machine source)."""
    return Markdown(
        f"```{lang}\n{body or ''}\n```",
        code_theme=CODE_THEME,
        hyperlinks=False,
    )


def labeled_fenced(label_markup: str, body: str, lang: str = "") -> RenderableType:
    """Chrome label + fenced body (slash-command observations)."""
    return Group(Text.from_markup(label_markup), fenced(body, lang=lang))


# -- activity tree labels (Textual Tree accepts Rich Text) -------------------


def tree_turn(title: str) -> Text:
    """Turn root: user text is plain bold (never markup-interpolated)."""
    line = Text()
    line.append(title or "", style="bold")
    return line


def tree_run(machine: str) -> Text:
    """Run node label: machine name only.

    Textual Tree already draws the expand toggle (▶/▼); do not prefix another ▶.
    """
    line = Text()
    line.append(machine or "", style="bold")
    return line


def tree_run_finished(machine: str, status: str, error: str | None = None) -> Text:
    glyph = {"done": "✓", "suspended": "⏸", "halt": "!"}.get(status, "•")
    style = {"done": "green", "suspended": "yellow", "halt": "red"}.get(status, "dim")
    line = Text(f"{glyph} ", style=style)
    line.append(machine or "run", style="bold")
    line.append(f"  {status}", style=style)
    if error:
        line.append(f" · {error}", style="dim")
    return line


def tree_state_start(state: str, kind: str, tier: str) -> Text:
    kind_style = {
        "tool": "yellow",
        "generative": "cyan",
        "gate": "magenta",
        "accumulate": "blue",
    }.get(kind, "dim")
    line = Text("◐ ", style="yellow")
    line.append(state or "", style="bold")
    if kind or tier:
        line.append("  ")
        line.append(f"{kind or 'state'}·{tier or 'default'}", style=kind_style)
    return line


def tree_state_done(state: str, policy: str | None, to: str | None) -> Text:
    """Match prior UX: ``● state {dim policy} → to`` or ``● state {dim policy} (policy)``."""
    policy_style = {
        "ok": "green",
        "fail": "red",
        "halt": "red",
        "suspend": "yellow",
    }.get(str(policy), "dim")
    line = Text("● ", style=policy_style)
    line.append(state or "", style="bold")
    line.append(" ")
    if policy is not None:
        line.append(str(policy), style=policy_style)
        line.append(" ")
    if to:
        line.append(f"→ {to}")
    else:
        line.append(f"({policy})" if policy is not None else "(—)")
    return line


def tree_preview(preview: str, limit: int = PREVIEW_MAX) -> Text:
    """Output preview leaf: plain dim text (not Markdown)."""
    text = preview if isinstance(preview, str) else str(preview or "")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return Text(text, style="dim")


def tree_branch(index: object) -> Text:
    return Text(f"· branch {index}", style="dim")


def status_line(
    state: str, provider: str, phase: str, spent_in: int, spent_out: int, session: str
) -> Text:
    """Render the operator HUD without treating runtime data as markup."""
    normalized = state.lower()
    glyph = STATUS_GLYPHS.get(normalized, "•")
    style = {
        "ready": "green",
        "running": "cyan",
        "waiting": "yellow",
        "stopping": "yellow",
        "error": "red",
    }.get(normalized, "dim")
    line = Text()
    line.append(f"{glyph} {normalized.upper()}", style=f"bold {style}")
    if phase:
        line.append(f"  {phase}", style="bold")
    line.append(
        f"  ·  {provider}  ·  tokens {spent_in}+{spent_out}  ·  session {session}",
        style="dim",
    )
    return line
