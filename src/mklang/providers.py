"""Provider adapter registry: builtins + ``mklang.providers`` entry-point plugins.

A provider factory is a callable ``(ProviderConfig) -> LLM`` — the returned
object must expose ``produce(...)`` and ``judge(...)`` (see ``llm/base.py``).
The CLI resolves the active provider name against this registry; any name not
registered falls back to the OpenAI-compatible adapter, which serves every
OpenAI-protocol provider (deepseek, openai, xai, mistral, openrouter, local, …).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib.metadata import entry_points

from .config import ProviderConfig

ENTRY_POINT_GROUP = "mklang.providers"

_log = logging.getLogger("mklang.providers")

ProviderFactory = Callable[[ProviderConfig], object]


def anthropic(prov: ProviderConfig):
    from .llm.anthropic import AnthropicLLM

    return AnthropicLLM(prov.api_key, prov.base_url)


def openai_compat(prov: ProviderConfig):
    from .llm.openai_compat import OpenAICompatLLM

    return OpenAICompatLLM(prov.api_key, prov.base_url)


# Only protocol-distinct adapters need a named entry; OpenAI-compatible is the default.
BUILTINS: dict[str, ProviderFactory] = {"anthropic": anthropic}


def load_entry_point_providers(group: str = ENTRY_POINT_GROUP) -> dict[str, ProviderFactory]:
    """Load third-party provider factories from packaging entry points.

    Failures are skipped with a WARNING log line so a broken plugin cannot sink the CLI.
    """
    reg: dict[str, ProviderFactory] = {}
    try:
        eps = entry_points()
        selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])
    except Exception as e:
        _log.warning("could not read entry points (%s): %s", group, e)
        return reg
    for ep in selected:
        try:
            reg[ep.name] = ep.load()
        except Exception as e:
            _log.warning("provider plugin %r failed to load: %s", ep.name, e)
    return reg


def load_provider_registry(
    extra: dict[str, ProviderFactory] | None = None,
    *,
    include_entry_points: bool = True,
) -> dict[str, ProviderFactory]:
    """Builtins ← entry-point plugins ← ``extra`` (later keys win)."""
    reg = dict(BUILTINS)
    if include_entry_points:
        reg.update(load_entry_point_providers())
    if extra:
        reg.update(extra)
    return reg


def build_llm(prov: ProviderConfig):
    """Resolve the provider name to a factory; default to the OpenAI-compatible adapter."""
    return load_provider_registry().get(prov.name, openai_compat)(prov)
