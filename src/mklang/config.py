"""Runtime configuration: load the tier->model map for a provider, keys from .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import find_dotenv, load_dotenv


@dataclass
class ProviderConfig:
    name: str
    tiers: dict[str, str]  # fast/balanced/reasoning -> model id
    api_key: str = ""
    base_url: str | None = None
    judge: str | None = None
    params: dict = field(default_factory=dict)

    def judge_override(self) -> str | None:
        """The optional global judge-model override (config `judge:`).

        ``None`` means gate judging follows each state's own capability tier
        (SPEC §2.1) — a `reasoning` state's gates are judged by the reasoning
        model, not silently downgraded. Set `judge:` only to force one cheaper
        model for *all* gates as a cost optimization."""
        return self.judge


def load_provider(config_path: str, provider: str | None = None) -> ProviderConfig:
    """Load a provider block from the runtime YAML; resolve its key from the env.

    `.env` is loaded first (python-dotenv), so keys never live in the config file."""
    load_dotenv(find_dotenv(usecwd=True))  # search from cwd upward, not the package dir
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    name = provider or cfg["active"]
    if name not in cfg.get("providers", {}):
        raise KeyError(f"provider {name!r} not in {config_path}")
    p = cfg["providers"][name]
    api_key = os.environ.get(p.get("api_key_env", ""), "")
    return ProviderConfig(
        name=name,
        tiers=p["tiers"],
        api_key=api_key,
        base_url=p.get("base_url"),
        judge=p.get("judge"),
        params=p.get("params", {}) or {},
    )
