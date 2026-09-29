"""Typed errors the adapters raise and the engine maps to halt reasons."""

from __future__ import annotations


class MklangError(Exception):
    """Base class for mklang runtime errors."""


class ProviderError(MklangError):
    """A provider/API call failed (after retries)."""


class CancellationError(MklangError):
    """The host requested cancellation while a provider was streaming."""


class ProviderConfigError(MklangError):
    """The configured provider cannot be resolved to a valid adapter."""


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


class OutputRejected(MklangError):
    """A produce call answered (and was billed) but its answer was refused.

    Raised for a truncated answer under ``on_truncate: halt`` and for a ``parse:``
    failure. Carries the call's tokens so the halt still charges them; ``error``
    is the halt detail (``output-truncated``, ``parse-json: …``).
    """

    def __init__(self, error: str, input_tokens: int = 0, output_tokens: int = 0):
        super().__init__(error)
        self.error = error
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class JudgeUnparseable(MklangError):
    """The gate judge returned text that could not be parsed as a choice."""
