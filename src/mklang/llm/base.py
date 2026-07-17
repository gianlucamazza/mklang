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
    # Output anti-cutoff (ADR 0018): adapters set truncated when the provider
    # stopped for length/max_tokens; finish_reason is the normalized stop label.
    truncated: bool = False
    finish_reason: str | None = None


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
    ) -> int | tuple[int, str | None]:
        """Return the 0-based index of the FIRST condition that holds (fused judge).

        The reference adapters return ``(index, method)`` where ``method`` is how the
        reply was parsed (``"json"`` / ``"bare"`` / ``"last-number"``, see
        ``parse_choice``); the engine traces a non-``json`` method as ``judge_parse``.
        Returning a bare ``int`` is also accepted (the engine treats the method as
        unknown) — mock/scripted judges use that simpler form.

        When the state used `reason: true`, `reasoning` is the private chain-of-thought
        (SPEC §4.5 / §6) — visible to the judge, never deposited into context."""
        ...


JUDGE_SYSTEM = (
    "You are the transition judge of a state machine. Given the state's OUTPUT and "
    "CONTEXT (and REASONING when present), return the NUMBER of the FIRST condition "
    "that is TRUE. Conditions are numbered 1..N (1-based). The condition 'otherwise' "
    "is always true. "
    'Reply with ONLY a JSON object: {"choice": <number>}. '
    "Do not include any other numbers in your reply."
)

# Host MAY truncate judge CONTEXT; reference adapters use this cap (SPEC §5 / ADR 0017).
JUDGE_CONTEXT_CHARS = 4000

# Provider-normalized stop reasons that mean the completion hit a token/length cap.
LENGTH_FINISH_REASONS = frozenset({"length", "max_tokens", "model_context_window_exceeded"})


def is_length_stop(reason: str | None) -> bool:
    """True when a provider stop/finish reason indicates output was cut off."""
    if not reason:
        return False
    return reason.lower() in LENGTH_FINISH_REASONS

# Transient HTTP statuses worth retrying (rate limits, gateway, overload).
TRANSIENT_STATUS = (408, 409, 429, 500, 502, 503, 504)


def parse_choice(text: str, n: int) -> tuple[int | None, str | None]:
    """Read the judge's choice, returning ``(index, method)``.

    Conditions are **1-based** in the prompt; the returned ``index`` is **0-based**
    in ``[0, n)``. Fallback order (a verbose or reasoning judge may not emit clean
    JSON, and ``max_tokens`` can truncate a trailing object):

    1. strict JSON ``{"choice": k}`` → method ``"json"``;
    2. a bare number, only if the **entire stripped reply** is digits → ``"bare"``;
    3. otherwise the **last** run of digits in the reply (models conclude with the
       answer) → ``"last-number"``.

    Returns ``(None, None)`` if nothing parses **or** the converted index is out of
    range. Callers must not clamp: out-of-range is an anomaly (soft-fall to
    ``otherwise`` or hard-halt ``judge-unparseable``), never a silent correction.
    The ``"last-number"`` method is anomaly-adjacent — the engine traces it as
    ``judge_parse`` without treating it as a fallback or a halt.
    """

    def _bounded(raw: int, method: str) -> tuple[int | None, str | None]:
        return (raw, method) if 0 <= raw < n else (None, None)

    s = (text or "").strip()
    # (a) strict JSON {"choice": k}
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "choice" in obj:
            return _bounded(int(obj["choice"]) - 1, "json")
    except (ValueError, TypeError):
        pass
    # (b) bare number: the entire stripped reply is a single integer
    if re.fullmatch(r"\d+", s):
        return _bounded(int(s) - 1, "bare")
    # (c) last number anywhere — the judge concluded with the answer
    nums = re.findall(r"\d+", s)
    if nums:
        return _bounded(int(nums[-1]) - 1, "last-number")
    return (None, None)
