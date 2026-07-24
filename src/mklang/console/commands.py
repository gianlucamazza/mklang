"""Slash-command metadata and shell-like parsing for the console."""

from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    usage: str
    description: str


COMMANDS = (
    SlashCommand("help", "/help", "Show commands and keyboard shortcuts"),
    SlashCommand("machines", "/machines", "List commissionable machines"),
    SlashCommand("run", "/run <name> [k=v ...]", "Run a machine directly"),
    SlashCommand("check", "/check <name>", "Validate a workspace machine"),
    SlashCommand("read", "/read <name>", "Show a workspace machine"),
    SlashCommand("budget", "/budget <positive tokens>", "Set the default run budget"),
    SlashCommand("resume", "/resume [index]", "List or resume a parked turn"),
    SlashCommand("session", "/session", "Show current session details"),
    SlashCommand("quit", "/quit", "Exit the console"),
)
BY_NAME = {f"/{command.name}": command for command in COMMANDS}


def parse_command(text: str) -> tuple[str, list[str]]:
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        raise ValueError(f"cannot parse command: {exc}") from exc
    if not parts:
        raise ValueError("empty command")
    return parts[0].lower(), parts[1:]


def parse_assignments(args: list[str]) -> dict[str, object]:
    """Parse slash-command ``key=value`` arguments without dropping input."""
    from ..cli import _coerce

    values: dict[str, object] = {}
    for arg in args:
        if "=" not in arg:
            raise ValueError(f"expected key=value, got {arg!r}")
        key, value = arg.split("=", 1)
        if not key.strip():
            raise ValueError("assignment key cannot be empty")
        values[key.strip()] = _coerce(value)
    return values


def help_text() -> str:
    width = max(len(command.usage) for command in COMMANDS)
    rows = [f"{command.usage:<{width}}  {command.description}" for command in COMMANDS]
    rows.append('Examples: /run std_cot task="2 + 2" · /check demo · /resume 0')
    rows.append("F2 inspector · Ctrl+T activity · Ctrl+G stop · Ctrl+L clear")
    return "\n".join(rows)
