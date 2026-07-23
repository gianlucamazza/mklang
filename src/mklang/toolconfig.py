"""Declarative tool-backend bindings from the runtime config (ADR 0016).

`runtime.yaml` may carry an optional ``tools:`` block binding each builtin
host tool to a backend. Precedence per knob, echoing the per-key `.env`
layering of ADR 0023: ``configure_*()`` programmatic binding > explicit
``MKLANG_*`` env var > ``tools:`` config > built-in default. The env var is
the operator's per-invocation override; the config is the persistent host or
project declaration. Secrets never live here — ``TAVILY_API_KEY`` stays in
the layered `.env` (ADR 0023).

`config.load_provider` publishes the parsed block process-wide; the tool
modules read the snapshot lazily at call time. Code that never loads a
runtime config sees an empty snapshot and keeps pure env behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolsConfig:
    search_backend: str | None = None
    kb_backend: str | None = None
    mail_backend: str | None = None
    fs_backend: str | None = None
    fs_workspace: str | None = None
    fs_write: bool | None = None


EMPTY = ToolsConfig()

_current: ToolsConfig | None = None


def _clean_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def parse_tools_block(cfg: dict) -> ToolsConfig:
    """Extract the ``tools:`` block defensively; junk shapes resolve to None.

    Schema validation is the doctor's job — runtime loading stays lax, like
    machine loading (ADR 0012)."""
    tools = cfg.get("tools") if isinstance(cfg, dict) else None
    if not isinstance(tools, dict):
        return EMPTY

    def section(name: str) -> dict:
        sec = tools.get(name)
        return sec if isinstance(sec, dict) else {}

    fs = section("fs")
    write = fs.get("write")
    return ToolsConfig(
        search_backend=_clean_str(section("search").get("backend")),
        kb_backend=_clean_str(section("kb").get("backend")),
        mail_backend=_clean_str(section("mail").get("backend")),
        fs_backend=_clean_str(fs.get("backend")),
        fs_workspace=_clean_str(fs.get("workspace")),
        fs_write=write if isinstance(write, bool) else None,
    )


def configure_tools(tc: ToolsConfig | None) -> None:
    """Publish (or clear) the process-wide tools-config snapshot."""
    global _current
    _current = tc


def current_tools() -> ToolsConfig:
    return _current if _current is not None else EMPTY
