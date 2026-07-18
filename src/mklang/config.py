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
    api_key_env: str = ""  # the env var the key is read from, for diagnostics
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


def load_env_files() -> tuple[str | None, str | None]:
    """Load the layered .env files; return the (project, user) paths that loaded.

    Layering is per key: real environment > project .env > user config .env.
    load_dotenv never overrides keys that are already set, so loading the
    project file first makes it win per key while the user file fills the gaps."""
    from .paths import host_paths

    project_env = find_dotenv(usecwd=True) or None
    if project_env:
        load_dotenv(project_env)
    user_env = host_paths().user_env
    if user_env.is_file():
        load_dotenv(user_env)
        return project_env, str(user_env)
    return project_env, None


def load_provider(config_path: str | Path | None, provider: str | None = None) -> ProviderConfig:
    """Load a provider block from the runtime YAML; resolve its key from the env.

    `.env` is loaded first (python-dotenv), so keys never live in the config file."""
    from .paths import resolve_config

    resolved = resolve_config(config_path)
    load_env_files()
    try:
        cfg = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read runtime config {resolved}: {exc}") from exc
    if not isinstance(cfg, dict) or not isinstance(cfg.get("providers"), dict):
        raise ValueError(f"runtime config {resolved} must define `active` and `providers`")
    name = provider or cfg["active"]
    if name not in cfg.get("providers", {}):
        raise ValueError(f"provider {name!r} not in {resolved}")
    p = cfg["providers"][name]
    api_key = os.environ.get(p.get("api_key_env", ""), "")
    return ProviderConfig(
        name=name,
        tiers=p["tiers"],
        api_key=api_key,
        api_key_env=p.get("api_key_env", ""),
        base_url=p.get("base_url"),
        judge=p.get("judge"),
        params=p.get("params", {}) or {},
    )
