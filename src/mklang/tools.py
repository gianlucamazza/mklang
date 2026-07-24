"""Host tools for `tool` states. A tool is a callable `(dict) -> str`.

The interpreter receives a name→callable map via `run(..., tools=...)`. The CLI
merges package builtins with third-party plugins discovered from the
``mklang.tools`` entry-point group (see ``load_tool_registry``).

I/O tools (search, search_kb, send_reply) follow the **stub architecture**
(ADR 0020): structured JSON observations with ``tool`` / ``stub`` / ``error``.
``calc`` is a pure offline evaluator (not a network stub). Filesystem data
tools (list_files, read_file, write_file) use the coding-tool workspace model
(ADR 0024): live reads confined to a workspace root, grant-gated writes.
"""

from __future__ import annotations

import ast
import logging
import operator
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

ToolFn = Callable[[dict], str]

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
# Annotated: pos/neg are overloaded, so an inferred value type would collapse
# to a non-callable join.
_UNARY: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


def calc(inp: dict) -> str:
    """Evaluate a safe arithmetic expression. Input: {"expr": "(17+4)*3"}.

    Pure offline tool — returns a plain numeric string (or ``error: …``), not
    the I/O JSON envelope (ADR 0020).
    """
    expr = str(inp.get("expr") or inp.get("query") or "").strip()
    try:
        return str(_eval(ast.parse(expr, mode="eval")))
    except Exception as e:  # return the error as an observation
        return f"error: could not evaluate {expr!r} ({e})"


def search(inp: dict) -> str:
    """Web search host tool (ADR 0016 / 0020).

    Offline by default (structured stub). Bind a real backend via
    ``mklang.search.configure_search`` or env ``MKLANG_SEARCH_BACKEND``
    (``fake`` / ``tavily`` + ``TAVILY_API_KEY``).
    """
    from .search import search as _search

    return _search(inp)


def search_kb(inp: dict) -> str:
    """Knowledge-base lookup (ADR 0020).

    Structured stub/fake by default. Configure via ``mklang.kb.configure_kb``
    or ``MKLANG_KB_BACKEND=fake|stub``. Production: entry points / ``run(tools=…)``.
    """
    from .kb import search_kb as _kb

    return _kb(inp)


def list_files(inp: dict) -> str:
    """List a workspace directory (ADR 0024).

    Live by default under the resolved workspace (``MKLANG_FS_ROOT`` or cwd);
    ``MKLANG_FS_BACKEND=stub`` forces the offline refusal tier.
    """
    from .fs import list_files as _list

    return _list(inp)


def read_file(inp: dict) -> str:
    """Read a workspace file, size-capped (ADR 0024). Same tiers as list_files."""
    from .fs import read_file as _read

    return _read(inp)


def write_file(inp: dict) -> str:
    """Write a workspace file (ADR 0024).

    Disk writes need an explicit grant: ``--allow-write`` / ``MKLANG_FS_WRITE=1``
    / ``mklang.fs.allow_writes``. Overwrite requires ``overwrite: true``.
    """
    from .fs import write_file as _write

    return _write(inp)


def send_reply(inp: dict) -> str:
    """Customer-reply sender (ADR 0020).

    Default stub records intent with ``sent: false`` — does not pretend mail left
    the host. Fake: ``MKLANG_MAIL_BACKEND=fake`` or ``configure_mail``.
    """
    from .mail import send_reply as _send

    return _send(inp)


BUILTINS: dict[str, ToolFn] = {
    "calc": calc,
    "search": search,
    "search_kb": search_kb,
    "send_reply": send_reply,
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
}

ENTRY_POINT_GROUP = "mklang.tools"

_log = logging.getLogger("mklang.tools")


def load_entry_point_tools(group: str = ENTRY_POINT_GROUP) -> dict[str, ToolFn]:
    """Load third-party tools from packaging entry points.

    Each entry point name becomes the tool name; the loaded object must be a
    callable ``(dict) -> str`` (or a factory returning one). Failures are skipped
    with a stderr warning so a broken plugin cannot sink the CLI.
    """
    reg: dict[str, ToolFn] = {}
    try:
        eps = entry_points()
        selected = eps.select(group=group)
    except Exception as e:
        _log.warning("could not read entry points (%s): %s", group, e)
        return reg
    for ep in selected:
        try:
            from .plugin_policy import allowed_plugin

            if not allowed_plugin(ep.name):
                _log.warning("tool plugin %r blocked by MKLANG_ALLOWED_PLUGINS", ep.name)
                continue
            obj = ep.load()
            if not callable(obj):
                raise TypeError(f"{ep.name} is not callable")
            reg[ep.name] = obj
        except Exception as e:
            _log.warning("tool plugin %r failed to load: %s", ep.name, e)
    return reg


def load_tool_registry(
    extra: dict[str, ToolFn] | None = None,
    *,
    include_entry_points: bool = True,
) -> dict[str, ToolFn]:
    """Builtins ← entry-point plugins ← ``extra`` (later keys win)."""
    reg = dict(BUILTINS)
    if include_entry_points:
        reg.update(load_entry_point_tools())
    if extra:
        reg.update(extra)
    return reg
