"""Provider adapter registry: builtins, entry-point plugins, and the default fallback."""

from mklang.config import ProviderConfig
from mklang.providers import BUILTINS, build_llm, load_provider_registry, openai_compat


def _prov(name):
    return ProviderConfig(name=name, tiers={"balanced": "m"}, api_key="k", base_url="http://x")


def test_builtin_anthropic_registered():
    reg = load_provider_registry(include_entry_points=False)
    assert reg["anthropic"] is BUILTINS["anthropic"]


def test_entry_point_provider_resolves():
    # The package's own entry point (pyproject) must round-trip through metadata.
    reg = load_provider_registry()
    assert "anthropic" in reg


def test_unknown_provider_falls_back_to_openai_compat():
    llm = build_llm(_prov("deepseek"))
    assert type(llm).__name__ == "OpenAICompatLLM"


def test_anthropic_uses_native_adapter():
    import pytest

    pytest.importorskip("anthropic")  # optional extra: mklang[anthropic]
    llm = build_llm(_prov("anthropic"))
    assert type(llm).__name__ == "AnthropicLLM"


def test_extra_override_wins():
    sentinel = object()
    reg = load_provider_registry({"deepseek": lambda prov: sentinel})
    assert reg["deepseek"](_prov("deepseek")) is sentinel
    assert load_provider_registry().get("nope", openai_compat) is openai_compat
