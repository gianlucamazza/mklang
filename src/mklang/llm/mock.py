"""Deterministic scripted LLM for tests — no network, fully reproducible."""

from __future__ import annotations

from collections.abc import Callable

from ..errors import JudgeUnparseable
from .base import LLMDelta, LLMEvent, Produced


class MockLLM:
    """produce_fn/judge_fn inspect the call args and return deterministic results.

    Defaults: echo a fixed answer, always pick the last condition. ``judge_fn``
    receives the author conditions only; returning ``len(conditions)`` selects the
    synthetic *none of the above* option (SPEC §5) when the engine offered it."""

    def __init__(
        self,
        produce_fn: Callable[..., Produced] | None = None,
        judge_fn: Callable[..., int] | None = None,
    ):
        self._produce = produce_fn
        self._judge = judge_fn
        self.calls: list[dict] = []  # records produce calls (for assertions)
        self.judge_calls: list[dict] = []  # records judge calls (model per gate eval)

    def produce(
        self,
        model: str,
        system: str,
        user: str,
        reason: bool = False,
        temperature: float = 0.4,
        params: dict | None = None,
        on_event: LLMEvent | None = None,
        on_delta: LLMDelta | None = None,
    ) -> Produced:
        self.calls.append({"model": model, "reason": reason, "params": params or {}})
        if self._produce:
            return self._produce(model, system, user, reason)
        produced = Produced(text="ok", reasoning=("thought" if reason else None))
        if on_delta is not None:
            if produced.reasoning:
                on_delta(produced.reasoning, "reasoning")
            on_delta(produced.text, "content")
        return produced

    def judge(
        self,
        model: str,
        conditions: list[str],
        output: str,
        context: dict,
        reasoning: str | None = None,
        allow_none: bool = False,
        on_event: LLMEvent | None = None,
    ) -> int:
        self.judge_calls.append(
            {"model": model, "conditions": list(conditions), "allow_none": allow_none}
        )
        if self._judge:
            # Pass reasoning only when the callback accepts it (existing tests use *a / 4 args).
            try:
                return self._judge(model, conditions, output, context, reasoning)
            except TypeError:
                return self._judge(model, conditions, output, context)
        return len(conditions) - 1


class UnparseableJudgeLLM(MockLLM):
    """Judge always raises JudgeUnparseable (for engine fallback tests)."""

    def judge(
        self,
        model: str,
        conditions: list[str],
        output: str,
        context: dict,
        reasoning: str | None = None,
        allow_none: bool = False,
    ) -> int:
        raise JudgeUnparseable("not a choice")
