"""Shared CLI presentation: typed results rendered as Rich text or stable JSON."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from functools import cache

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Human-readable explanations for runtime halt errors.
# Keys are the exact error strings from engine.py; values are (summary, hint) pairs.
# The hint explains what the author should do — never a traceback.
_ERROR_HINTS: dict[str, tuple[str, str]] = {
    "budget-exhausted": (
        "The run consumed all available steps.",
        "Increase `budget:` in the machine, or reduce repair loops and fan-out width. "
        "A fan-out `over: {{list}}` with N items charges N steps, not 1.",
    ),
    "cost-exhausted": (
        "The shared token cost budget was reached.",
        "Increase `--max-tokens` or reduce the machine's step budget "
        "(fewer steps = fewer LLM calls).",
    ),
    "loop-ceiling": (
        "A state was entered more times than allowed.",
        "Check for unbounded repair loops. Add a `max_visits:` ceiling or a "
        "`when: otherwise` exit gate.",
    ),
    "call-failed": (
        "A sub-machine halted; the parent cannot continue with an empty result.",
        "Inspect the sub-run trace. The child's error is included in the message.",
    ),
    "call-depth-exceeded": (
        "Machine recursion exceeded the maximum depth.",
        "Remove or reduce recursive `call:` chains.",
    ),
    "no-gate-matched": (
        "No gate condition was true and there is no `when: otherwise` catch-all.",
        "Add a `when: otherwise` gate as the last gate in the state, or review gate conditions.",
    ),
    "judge-unparseable": (
        "The gate judge returned text that could not be parsed as a choice number.",
        "This usually means the judge model was too verbose. Use a non-reasoning "
        "model for judging, "
        "or add a `when: otherwise` fallback gate.",
    ),
    "refusal": (
        "The model declined to answer.",
        "Check the prompt and execution policy. Some providers refuse content they "
        "classify as unsafe.",
    ),
    "gate-fail": (
        "A gate explicitly chose `fail: true`.",
        "This is intentional — the machine author designed this failure path. Check "
        "the trace for which gate fired.",
    ),
    "untrusted-control-flow": (
        "A tainted decision reached an effectful tool state.",
        "The host policy is 'report' by default. Use --untrusted-flow halt to refuse, "
        "or add a hook: gate to confirm the transition.",
    ),
    "cancelled": (
        "The run was cancelled.",
        "",
    ),
    "resume-mismatch": (
        "The machine changed since the checkpoint was created.",
        "Resume with a compatible version of the machine, or create a new checkpoint.",
    ),
}


@cache
def error_hint(error_code: str) -> tuple[str, str]:
    """Return (summary, hint) for a runtime error code.

    Falls back to a neutral explanation when the code is not in the map.
    Results are cached so the lookup is O(1) after the first call.
    """
    return _ERROR_HINTS.get(
        error_code,
        (
            f"Run halted: {error_code}",
            "Check the trace for the failing state. Run `mklang lint --strict` to "
            "validate the machine.",
        ),
    )


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
        err = str(out["error"])
        summary, hint = error_hint(err)
        console.print(f"[red]Error:[/red] {summary}")
        if hint:
            console.print(f"  [dim]Hint:[/dim] {hint}")
    if out.get("diagnosis"):
        d = out["diagnosis"]
        console.print(
            f"[dim]most revisited: {d.get('most_visited_state')} x{d.get('visits')}[/dim]"
        )
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
