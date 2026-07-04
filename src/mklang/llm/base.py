"""The LLM interface the engine talks to. Two operations: produce and judge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class Produced:
    text: str
    reasoning: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class LLM(Protocol):
    def produce(
        self,
        model: str,
        system: str,
        user: str,
        reason: bool = False,
        temperature: float = 0.4,
        params: dict | None = None,
    ) -> Produced:
        """Generate a state's output; capture reasoning when `reason` is set.

        `params` carries provider-specific per-tier knobs (effort, thinking,
        reasoning_effort, …) from the runtime config; adapters apply what they can."""
        ...

    def judge(self, model: str, conditions: list[str], output: str, context: dict) -> int:
        """Return the 0-based index of the FIRST condition that holds (fused judge)."""
        ...


JUDGE_SYSTEM = (
    "You are the transition judge of a state machine. Given the state's OUTPUT and "
    "CONTEXT, return the NUMBER of the FIRST condition that is TRUE. The condition "
    "'otherwise' is always true. Reply with ONLY the number."
)
