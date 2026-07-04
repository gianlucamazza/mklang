"""Deterministic scripted LLM for tests — no network, fully reproducible."""

from __future__ import annotations

from collections.abc import Callable

from .base import Produced


class MockLLM:
    """produce_fn/judge_fn inspect the call args and return deterministic results.

    Defaults: echo a fixed answer, always pick the last (catch-all) condition."""

    def __init__(
        self,
        produce_fn: Callable[..., Produced] | None = None,
        judge_fn: Callable[[str, list[str], str, dict], int] | None = None,
    ):
        self._produce = produce_fn
        self._judge = judge_fn
        self.calls: list[dict] = []  # records produce calls (for assertions)

    def produce(self, model, system, user, reason=False, temperature=0.4, params=None) -> Produced:
        self.calls.append({"model": model, "reason": reason, "params": params or {}})
        if self._produce:
            return self._produce(model, system, user, reason)
        return Produced(text="ok", reasoning=("thought" if reason else None))

    def judge(self, model, conditions, output, context) -> int:
        if self._judge:
            return self._judge(model, conditions, output, context)
        return len(conditions) - 1
