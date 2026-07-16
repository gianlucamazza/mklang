"""The LLM interface the engine talks to. Two operations: produce and judge."""

from __future__ import annotations

import json
import re
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

    def judge(
        self,
        model: str,
        conditions: list[str],
        output: str,
        context: dict,
        reasoning: str | None = None,
    ) -> int:
        """Return the 0-based index of the FIRST condition that holds (fused judge).

        When the state used `reason: true`, `reasoning` is the private chain-of-thought
        (SPEC §4.5 / §6) — visible to the judge, never deposited into context."""
        ...


JUDGE_SYSTEM = (
    "You are the transition judge of a state machine. Given the state's OUTPUT and "
    "CONTEXT (and REASONING when present), return the NUMBER of the FIRST condition "
    "that is TRUE. The condition 'otherwise' is always true. "
    'Reply with ONLY a JSON object: {"choice": <number>}.'
)

# Transient HTTP statuses worth retrying (rate limits, gateway, overload).
TRANSIENT_STATUS = (408, 409, 429, 500, 502, 503, 504)


def parse_choice(text: str, n: int) -> int | None:
    """Read the judge's choice: JSON {"choice": k} first, then a bare number.

    Returns a 0-based index, or **None** if the text is unparseable. Callers clamp
    to ``[0, n)`` and decide soft-fallback vs hard-fail (never silently invent a
    choice without recording it). ``n`` is accepted for API stability; out-of-range
    indices are returned as-is for the caller to clamp."""
    del n  # reserved for future bounded parsing; clamp stays at the call site
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "choice" in obj:
            return int(obj["choice"]) - 1
    except (ValueError, TypeError):
        pass
    m = re.search(r"\d+", text or "")
    return int(m.group()) - 1 if m else None