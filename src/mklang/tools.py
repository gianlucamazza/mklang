"""Host tools for `tool` states. A tool is a callable `(dict) -> str`.

The interpreter receives a name→callable map via `run(..., tools=...)`. The CLI
merges package builtins with third-party plugins discovered from the
``mklang.tools`` entry-point group (see ``load_tool_registry``).
"""

from __future__ import annotations

import ast
import operator
import sys
from collections.abc import Callable
from importlib.metadata import entry_points

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
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval(node):
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
    """Evaluate a safe arithmetic expression. Input: {"expr": "(17+4)*3"}."""
    expr = str(inp.get("expr") or inp.get("query") or "").strip()
    try:
        return str(_eval(ast.parse(expr, mode="eval")))
    except Exception as e:  # noqa: BLE001 — return the error as an observation
        return f"error: could not evaluate {expr!r} ({e})"


def search(inp: dict) -> str:
    """Stub search — a real host binds a web/RAG tool here."""
    query = str(inp.get("query") or "").strip()
    return f"[no external search bound] query was: {query!r}"


BUILTINS: dict[str, ToolFn] = {"calc": calc, "search": search}

ENTRY_POINT_GROUP = "mklang.tools"


def load_entry_point_tools(group: str = ENTRY_POINT_GROUP) -> dict[str, ToolFn]:
    """Load third-party tools from packaging entry points.

    Each entry point name becomes the tool name; the loaded object must be a
    callable ``(dict) -> str`` (or a factory returning one). Failures are skipped
    with a stderr warning so a broken plugin cannot sink the CLI.
    """
    reg: dict[str, ToolFn] = {}
    try:
        eps = entry_points()
        selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])
    except Exception as e:  # noqa: BLE001
        print(f"# warning: could not read entry points ({group}): {e}", file=sys.stderr)
        return reg
    for ep in selected:
        try:
            obj = ep.load()
            if not callable(obj):
                raise TypeError(f"{ep.name} is not callable")
            reg[ep.name] = obj  # type: ignore[assignment]
        except Exception as e:  # noqa: BLE001
            print(f"# warning: tool plugin {ep.name!r} failed to load: {e}", file=sys.stderr)
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
