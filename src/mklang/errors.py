"""Typed errors the adapters raise and the engine maps to halt reasons."""

from __future__ import annotations


class MklangError(Exception):
    """Base class for mklang runtime errors."""


class ProviderError(MklangError):
    """A provider/API call failed (after retries)."""


class RefusalError(MklangError):
    """The model declined to answer (e.g. Anthropic stop_reason == 'refusal')."""
