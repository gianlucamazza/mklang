"""Host gate hooks: callables `(context, output) -> bool`.

Optional `hook: <name>` on a gate evaluates the named predicate without the LLM
(ADR 0006 / SPEC §5). The CLI merges builtins with plugins from the
``mklang.hooks`` entry-point group (see ``load_hook_registry``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

HookFn = Callable[[dict, Any], bool]

ENTRY_POINT_GROUP = "mklang.hooks"

_log = logging.getLogger("mklang.hooks")


def always_true(_ctx: dict, _output: Any) -> bool:
    return True


def always_false(_ctx: dict, _output: Any) -> bool:
    return False


def amount_le_100(ctx: dict, _output: Any) -> bool:
    """True when context `amount` is a number ≤ 100 (demo auto-approve)."""
    amount = ctx.get("amount")
    if amount is None:
        return False
    try:
        return float(amount) <= 100
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


def load_entry_point_hooks(group: str = ENTRY_POINT_GROUP) -> dict[str, HookFn]:
    """Load third-party hooks from packaging entry points (name → callable)."""
    reg: dict[str, HookFn] = {}
    try:
        eps = entry_points()
        selected = eps.select(group=group)
    except Exception as e:
        _log.warning("could not read entry points (%s): %s", group, e)
        return reg
    for ep in selected:
        try:
            obj = ep.load()
            if not callable(obj):
                raise TypeError(f"{ep.name} is not callable")
            reg[ep.name] = obj
        except Exception as e:
            _log.warning("hook plugin %r failed to load: %s", ep.name, e)
    return reg


def load_hook_registry(
    extra: dict[str, HookFn] | None = None,
    *,
    include_entry_points: bool = True,
) -> dict[str, HookFn]:
    """Builtins ← entry-point plugins ← ``extra`` (later keys win)."""
    reg = dict(BUILTINS)
    if include_entry_points:
        reg.update(load_entry_point_hooks())
    if extra:
        reg.update(extra)
    return reg
