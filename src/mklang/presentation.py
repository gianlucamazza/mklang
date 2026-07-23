"""Shared CLI presentation: typed results rendered as Rich text or stable JSON."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@dataclass
class Diagnostic:
    severity: str
    message: str
    code: str = ""
    path: str = ""
    hint: str = ""


@dataclass
class CommandResult:
    command: str
    ok: bool
    items: list[dict] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def json_value(self) -> dict:
        return {
            "command": self.command,
            "ok": self.ok,
            "items": self.items,
            "diagnostics": [asdict(d) for d in self.diagnostics],
            "summary": self.summary,
        }


def output_format(requested: str, *, structured_default: bool = False) -> str:
    if requested != "auto":
        return requested
    return "json" if structured_default and not sys.stdout.isatty() else "text"


def console_for(color: str = "auto", *, stderr: bool = False) -> Console:
    no_color = color == "never" or (color == "auto" and "NO_COLOR" in os.environ)
    force = True if color == "always" else None
    return Console(stderr=stderr, no_color=no_color, force_terminal=force)


def emit_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def emit_result(
    result: CommandResult, *, fmt: str, color: str = "auto", stderr: bool = False
) -> None:
    if fmt == "json":
        emit_json(result.json_value())
        return
    console = console_for(color, stderr=stderr)
    for item in result.items:
        status = item.get("status", "ok")
        style = "green" if status in ("ok", "pass", "done") else "red"
        label = item.get("path") or item.get("name") or item.get("scenario") or "item"
        console.print(f"[{style}]{status.upper()}[/{style}] [bold]{label}[/bold]")
        for key in ("warnings", "errors", "findings", "llm_findings", "mismatches"):
            for message in item.get(key, []):
                marker = {
                    "warnings": "warning",
                    "errors": "error",
                    "findings": "lint",
                    "llm_findings": "llm",
                    "mismatches": "mismatch",
                }[key]
                console.print(f"  [dim]{marker}:[/dim] {message}")
    for diagnostic in result.diagnostics:
        style = {"warning": "yellow", "error": "red"}.get(diagnostic.severity, "cyan")
        prefix = f"{diagnostic.path}: " if diagnostic.path else ""
        console.print(
            f"[{style}]{diagnostic.severity.upper()}[/{style}] {prefix}{diagnostic.message}",
            soft_wrap=True,
        )
        if diagnostic.hint:
            console.print(f"  [dim]Hint: {diagnostic.hint}[/dim]", soft_wrap=True)
    if result.summary:
        console.print(
            Panel(" · ".join(f"{k}={v}" for k, v in result.summary.items()), title=result.command)
        )


def emit_run_text(out: dict, *, machine: str, provider: str, color: str = "auto") -> None:
    console = console_for(color)
    status = str(out.get("status", "unknown"))
    style = "green" if status == "done" else "yellow" if status == "suspended" else "red"
    console.print(
        f"[{style}]{status.upper()}[/{style}] [bold]{machine}[/bold] · provider {provider}"
    )
    if out.get("result") not in (None, ""):
        console.print(Panel(str(out["result"]), title="Result", border_style=style))
    usage = out.get("usage") or {}
    console.print(
        f"[dim]tokens {usage.get('input_tokens', 0)}+{usage.get('output_tokens', 0)}"
        f" · steps {len(out.get('trace') or [])}[/dim]"
    )
    if out.get("error"):
        console.print(f"[red]Error:[/red] {out['error']}")
    if out.get("checkpoint"):
        console.print(f"[yellow]Checkpoint:[/yellow] {out['checkpoint']}")


def emit_machines_text(rows: list[dict], *, color: str = "auto") -> None:
    table = Table(title="Commissionable machines", header_style="bold")
    for heading in ("Name", "Source", "Entry", "Result", "Budget", "Context"):
        table.add_column(heading)
    for row in rows:
        table.add_row(
            str(row.get("name", "")),
            str(row.get("source", "")),
            str(row.get("entry", "")),
            str(row.get("result", "—")),
            str(row.get("budget", "")),
            ", ".join((row.get("context") or {}).keys()) or "—",
        )
    console_for(color).print(table)
