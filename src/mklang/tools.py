"""Host tools for `tool` states. A tool is a callable `(dict) -> str`.

The interpreter passes a name→callable registry to `run(..., tools=...)`. Library
users supply their own; the CLI ships these deterministic demos so the examples run
offline."""

from __future__ import annotations

import ast
import operator

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


BUILTINS: dict[str, callable] = {"calc": calc, "search": search}
