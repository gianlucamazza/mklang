"""Provider adapter registry: builtins + ``mklang.providers`` entry-point plugins.

A provider factory is a callable ``(ProviderConfig) -> LLM`` — the returned
object must expose ``produce(...)`` and ``judge(...)`` (see ``llm/base.py``).
The CLI resolves the active provider name against this registry. OpenAI-compatible
providers are explicit aliases or must declare ``protocol: openai_compat`` in the
host config; unknown names never silently select an adapter.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib.metadata import entry_points

from .config import ProviderConfig
from .errors import ProviderConfigError
from .llm.base import LLM
from .llm.openai_compat import OpenAICompatLLM, OpenAICompatProfile

ENTRY_POINT_GROUP = "mklang.providers"

_log = logging.getLogger("mklang.providers")

ProviderFactory = Callable[[ProviderConfig], LLM]


def anthropic(prov: ProviderConfig) -> LLM:
    from .llm.anthropic import AnthropicLLM

    return AnthropicLLM(prov.api_key, prov.base_url)


def openai_compat(prov: ProviderConfig) -> LLM:
    profile = OPENAI_COMPAT_PROFILES.get(prov.name, OpenAICompatProfile())
    return OpenAICompatLLM(prov.api_key, prov.base_url, profile=profile)


# OpenAI-compatible aliases are explicit so a typo cannot silently select a protocol.
# ``protocol: openai_compat`` remains available for custom endpoints and plugins.
OPENAI_COMPAT_PROFILES = {
    "deepseek": OpenAICompatProfile(omit_temperature_when_thinking=True),
    # Hetzner Experiments documents chat completions, but not JSON response
    # format; keep the judge prompt self-contained on this experimental endpoint.
    "hetzner": OpenAICompatProfile(supports_response_format=False),
    # OpenAI's current GPT models reject max_tokens in favor of the newer name.
    "openai": OpenAICompatProfile(
        max_output_tokens_param="max_completion_tokens", supports_temperature=False
    ),
}
BUILTINS: dict[str, ProviderFactory] = {
    "anthropic": anthropic,
    **{
        name: openai_compat
        for name in (
            "deepseek",
            "hetzner",
            "openai",
            "google",
            "openrouter",
            "xai",
            "mistral",
            "local",
        )
    },
}


def load_entry_point_providers(group: str = ENTRY_POINT_GROUP) -> dict[str, ProviderFactory]:
    """Load third-party provider factories from packaging entry points.

    Failures are skipped with a WARNING log line so a broken plugin cannot sink the CLI.
    """
    reg: dict[str, ProviderFactory] = {}
    try:
        eps = entry_points()
        selected = eps.select(group=group)
    except Exception as e:
        _log.warning("could not read entry points (%s): %s", group, e)
        return reg
    for ep in selected:
        try:
            from .plugin_policy import allowed_plugin

            if not allowed_plugin(ep.name):
                _log.warning("provider plugin %r blocked by MKLANG_ALLOWED_PLUGINS", ep.name)
                continue
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


def build_llm(prov: ProviderConfig) -> LLM:
    """Resolve a registered provider or an explicitly declared protocol."""
    if prov.protocol == "openai_compat":
        return openai_compat(prov)
    registry = load_provider_registry()
    factory = registry.get(prov.name)
    if factory is not None:
        return factory(prov)
    raise ProviderConfigError(
        f"provider {prov.name!r} is not registered; configure an entry-point provider "
        "or set protocol: openai_compat"
    )
