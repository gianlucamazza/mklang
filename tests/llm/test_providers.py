"""Provider adapter registry: builtins, entry-point plugins, and explicit protocols."""

import pytest

from mklang import providers
from mklang.config import ProviderConfig
from mklang.errors import ProviderConfigError
from mklang.providers import BUILTINS, build_llm, load_provider_registry


def _prov(name):
    return ProviderConfig(name=name, tiers={"balanced": "m"}, api_key="k", base_url="http://x")


def test_builtin_anthropic_registered():
    reg = load_provider_registry(include_entry_points=False)
    assert reg["anthropic"] is BUILTINS["anthropic"]


def test_entry_point_provider_resolves():
    # The package's own entry point (pyproject) must round-trip through metadata.
    reg = load_provider_registry()
    assert "anthropic" in reg


def test_registered_openai_compatible_provider_uses_shared_adapter():
    llm = build_llm(_prov("deepseek"))
    assert type(llm).__name__ == "OpenAICompatLLM"
    assert llm.profile.omit_temperature_when_thinking is True


def test_hetzner_uses_compatible_profile_without_response_format():
    llm = build_llm(_prov("hetzner"))
    assert type(llm).__name__ == "OpenAICompatLLM"
    assert llm.profile.supports_response_format is False


def test_unknown_provider_requires_explicit_protocol():
    with pytest.raises(ProviderConfigError, match="not registered"):
        build_llm(_prov("typo"))


def test_custom_openai_compatible_provider_declares_protocol():
    llm = build_llm(
        ProviderConfig(name="custom", protocol="openai_compat", tiers={"balanced": "m"})
    )
    assert type(llm).__name__ == "OpenAICompatLLM"


def test_explicit_protocol_precedes_registered_name():
    llm = build_llm(
        ProviderConfig(name="anthropic", protocol="openai_compat", tiers={"balanced": "m"})
    )
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
    assert load_provider_registry().get("nope") is None


def test_provider_entry_points_honor_allowlist(monkeypatch, caplog):
    class EntryPoint:
        name = "blocked"

        @staticmethod
        def load():
            return lambda prov: object()

    class EntryPoints:
        @staticmethod
        def select(*, group):
            assert group == "mklang.providers"
            return [EntryPoint()]

    monkeypatch.setattr(providers, "entry_points", lambda: EntryPoints())
    monkeypatch.setenv("MKLANG_ALLOWED_PLUGINS", "allowed")
    with caplog.at_level("WARNING", logger="mklang.providers"):
        assert providers.load_entry_point_providers() == {}
    assert "blocked by MKLANG_ALLOWED_PLUGINS" in caplog.text
