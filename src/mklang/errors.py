"""Typed errors the adapters raise and the engine maps to halt reasons."""

from __future__ import annotations


class MklangError(Exception):
    """Base class for mklang runtime errors."""


class ProviderError(MklangError):
    """A provider/API call failed (after retries)."""


class RefusalError(MklangError):
    """The model declined to answer (e.g. Anthropic stop_reason == 'refusal')."""


class CallFailed(MklangError):
    """A sub-machine `call` halted; the parent run must halt too (not continue as done)."""

    def __init__(
        self,
        error: str,
        sub_trace: list | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        super().__init__(error)
        self.error = error
        self.sub_trace = sub_trace or []
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class JudgeUnparseable(MklangError):
    """The gate judge returned text that could not be parsed as a choice."""
