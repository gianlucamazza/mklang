"""Host gate hooks: callables `(context, output) -> bool`.

Optional `hook: <name>` on a gate evaluates the named predicate without the LLM
(ADR 0006 / SPEC §5). The CLI merges builtins with plugins from the
``mklang.hooks`` entry-point group (see ``load_hook_registry``).

Parametric builtins (no plugin install needed):

- ``eq:key:value`` / ``neq:key:value`` — string equality on a top-level context key
  (strip both sides). Example: ``hook: eq:emit_mode:full``.
- ``write_failed`` — true when the state output looks like a write_file observation
  with non-null ``error`` or ``written`` is false (JSON object or JSON string).
"""

from __future__ import annotations

import json
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


def write_failed(_ctx: dict, output: Any) -> bool:
    """True when output is a write_file-style observation that did not succeed."""
    obs: Any = output
    if isinstance(obs, str):
        try:
            obs = json.loads(obs)
        except (TypeError, ValueError):
            return False
    if not isinstance(obs, dict):
        return False
    if obs.get("error") is not None:
        return True
    return "written" in obs and obs.get("written") is False


def console_workspace_ready(ctx: dict, _output: Any) -> bool:
    """Allow the console brain to reply only after required workspace evidence."""
    if not ctx.get("workspace_required"):
        return True
    if not ctx.get("workspace_brief"):
        return False
    observations = ctx.get("observation")
    if not isinstance(observations, list):
        return False
    for observation in observations:
        if not isinstance(observation, str):
            continue
        try:
            payload = json.loads(observation)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("tool") in {
            "list_workspace",
            "read_workspace_file",
            "search_workspace",
        }:
            return True
    return False


def _context_eq(key: str, value: str, *, negate: bool = False) -> HookFn:
    def hook(ctx: dict, _output: Any, k: str = key, v: str = value, neg: bool = negate) -> bool:
        actual = str(ctx.get(k, "")).strip()
        match = actual == v
        return (not match) if neg else match

    return hook


def resolve_hook(name: str | None, hooks: dict[str, HookFn] | None = None) -> HookFn | None:
    """Look up a hook by name, including parametric ``eq:`` / ``neq:`` forms."""
    if not name:
        return None
    reg = hooks or {}
    if name in reg:
        return reg[name]
    if name in BUILTINS:
        return BUILTINS[name]
    if name.startswith("eq:") or name.startswith("neq:"):
        parts = name.split(":", 2)
        if len(parts) == 3 and parts[1]:
            kind, key, value = parts
            return _context_eq(key, value, negate=(kind == "neq"))
    return None


BUILTINS: dict[str, HookFn] = {
    "always_true": always_true,
    "always_false": always_false,
    "amount_le_100": amount_le_100,
    "has_receipt": has_receipt,
    "auto_approve_ok": auto_approve_ok,
    "write_failed": write_failed,
    "console_workspace_ready": console_workspace_ready,
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
            from .plugin_policy import allowed_plugin

            if not allowed_plugin(ep.name):
                _log.warning("hook plugin %r blocked by MKLANG_ALLOWED_PLUGINS", ep.name)
                continue
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
