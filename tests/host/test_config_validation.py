"""Runtime provider configuration rejects structurally invalid blocks early."""

import pytest
import yaml

from mklang.config import load_provider


def _write(tmp_path, provider):
    path = tmp_path / "runtime.yaml"
    path.write_text(yaml.safe_dump({"active": "custom", "providers": {"custom": provider}}))
    return path


def test_load_provider_rejects_missing_capability_tier(tmp_path):
    with pytest.raises(ValueError, match="exactly fast, balanced and reasoning"):
        load_provider(_write(tmp_path, {"tiers": {"balanced": "model"}}))


def test_load_provider_rejects_params_for_unknown_tier(tmp_path):
    provider = {
        "tiers": {"fast": "f", "balanced": "b", "reasoning": "r"},
        "params": {"unknown": {"effort": "high"}},
    }
    with pytest.raises(ValueError, match="unknown tier"):
        load_provider(_write(tmp_path, provider))


def test_load_provider_preserves_explicit_protocol(tmp_path):
    provider = {
        "protocol": "openai_compat",
        "tiers": {"fast": "f", "balanced": "b", "reasoning": "r"},
    }
    assert load_provider(_write(tmp_path, provider)).protocol == "openai_compat"


def test_bundled_hetzner_provider_configuration():
    provider = load_provider("config/runtime.example.yaml", "hetzner")
    assert provider.protocol == "openai_compat"
    assert provider.base_url == "https://inference.hetzner.com/api/v1"
    assert provider.api_key_env == "HETZNER_INFERENCE_API_KEY"
    assert set(provider.tiers) == {"fast", "balanced", "reasoning"}
    assert set(provider.tiers.values()) == {"Qwen/Qwen3.6-35B-A3B-FP8"}
