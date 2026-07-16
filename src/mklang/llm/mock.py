"""Deterministic scripted LLM for tests — no network, fully reproducible."""

from __future__ import annotations

from collections.abc import Callable

from ..errors import JudgeUnparseable
from .base import Produced


class MockLLM:
    """produce_fn/judge_fn inspect the call args and return deterministic results.

    Defaults: echo a fixed answer, always pick the last (catch-all) condition."""

    def __init__(
        self,
        produce_fn: Callable[..., Produced] | None = None,
        judge_fn: Callable[..., int] | None = None,
    ):
        self._produce = produce_fn
        self._judge = judge_fn
        self.calls: list[dict] = []  # records produce calls (for assertions)
        self.judge_calls: list[dict] = []  # records judge calls (model per gate eval)

    def produce(self, model, system, user, reason=False, temperature=0.4, params=None) -> Produced:
        self.calls.append({"model": model, "reason": reason, "params": params or {}})
        if self._produce:
            return self._produce(model, system, user, reason)
        return Produced(text="ok", reasoning=("thought" if reason else None))

    def judge(self, model, conditions, output, context, reasoning=None) -> int:
        self.judge_calls.append({"model": model, "conditions": list(conditions)})
        if self._judge:
            # Pass reasoning only when the callback accepts it (existing tests use *a / 4 args).
            try:
                return self._judge(model, conditions, output, context, reasoning)
            except TypeError:
                return self._judge(model, conditions, output, context)
        return len(conditions) - 1


class UnparseableJudgeLLM(MockLLM):
    """Judge always raises JudgeUnparseable (for engine fallback tests)."""

    def judge(self, model, conditions, output, context, reasoning=None) -> int:
        raise JudgeUnparseable("not a choice")
