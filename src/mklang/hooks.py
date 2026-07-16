"""Host gate hooks: callables `(context, output) -> bool`.

Optional `hook: <name>` on a gate evaluates the named predicate without the LLM
(ADR 0006 / SPEC §5). Library users pass `run(..., hooks=...)`; the CLI ships a
few deterministic demos for examples and tests.
"""

from __future__ import annotations

from typing import Any, Callable

HookFn = Callable[[dict, Any], bool]


def always_true(_ctx: dict, _output: Any) -> bool:
    return True


def always_false(_ctx: dict, _output: Any) -> bool:
    return False


def amount_le_100(ctx: dict, _output: Any) -> bool:
    """True when context `amount` is a number ≤ 100 (demo auto-approve)."""
    try:
        return float(ctx.get("amount")) <= 100
    except (TypeError, ValueError):
        return False


def has_receipt(ctx: dict, _output: Any) -> bool:
    """True when context `has_receipt` is truthy."""
    return bool(ctx.get("has_receipt"))


def auto_approve_ok(ctx: dict, output: Any) -> bool:
    """Receipt present and amount ≤ 100 — typical expense auto-approve rule."""
    return has_receipt(ctx, output) and amount_le_100(ctx, output)


BUILTINS: dict[str, HookFn] = {
    "always_true": always_true,
    "always_false": always_false,
    "amount_le_100": amount_le_100,
    "has_receipt": has_receipt,
    "auto_approve_ok": auto_approve_ok,
}
