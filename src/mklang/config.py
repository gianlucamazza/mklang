"""Runtime configuration: load the tier->model map for a provider, keys from .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import dotenv_values, find_dotenv


@dataclass
class ProviderConfig:
    name: str
    tiers: dict[str, str]  # fast/balanced/reasoning -> model id
    api_key: str = ""
    api_key_env: str = ""  # the env var the key is read from, for diagnostics
    api_key_file: str = ""  # optional user-owned file containing the key
    base_url: str | None = None
    judge: str | None = None
    params: dict = field(default_factory=dict)
    protocol: str = "auto"  # auto (registered provider) or openai_compat

    def judge_override(self) -> str | None:
        """The optional global judge-model override (config `judge:`).

        ``None`` means gate judging follows each state's own capability tier
        (SPEC §2.1) — a `reasoning` state's gates are judged by the reasoning
        model, not silently downgraded. Set `judge:` only to force one cheaper
        model for *all* gates as a cost optimization."""
        return self.judge


def load_env_files(*, cwd: Path | None = None) -> tuple[str | None, str | None]:
    """Load the layered .env files; return the (project, user) paths that loaded.

    Layering is per key: real environment > project .env > user config .env.
    Empty scaffold values do not block a non-empty user value. The process
    environment always wins, and values are installed explicitly so this
    function remains correct when called more than once in one process."""
    from .paths import host_paths

    if cwd is not None:
        project_env = (
            str(Path(cwd).resolve() / ".env") if (Path(cwd).resolve() / ".env").is_file() else None
        )
    else:
        project_env = find_dotenv(usecwd=True) or None

    def apply(path: str | Path | None) -> None:
        if not path:
            return
        for key, value in dotenv_values(path).items():
            if not key or value is None:
                continue
            # A real process value wins. Empty values from a scaffold are
            # placeholders and may be filled by the user layer.
            if key not in os.environ or not os.environ[key]:
                os.environ[key] = value

    apply(project_env)
    user_env = host_paths().user_env
    if user_env.is_file():
        apply(user_env)
        return project_env, str(user_env)
    return project_env, None


def _env_layers(cwd: Path | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """Read project/user dotenv values without mutating process environment."""
    from .paths import host_paths

    project = None
    if cwd is not None:
        candidate = Path(cwd).resolve() / ".env"
        project = str(candidate) if candidate.is_file() else None
    else:
        project = find_dotenv(usecwd=True) or None
    user = host_paths().user_env
    project_values = (
        {key: value for key, value in dotenv_values(project).items() if key and value is not None}
        if project
        else {}
    )
    user_values = (
        {key: value for key, value in dotenv_values(user).items() if key and value is not None}
        if user.is_file()
        else {}
    )
    return project_values, user_values


def load_provider(
    config_path: str | Path | None,
    provider: str | None = None,
    *,
    cwd: Path | None = None,
) -> ProviderConfig:
    """Load a provider block from the runtime YAML; resolve its key from the env.

    Dotenv files are read as layered values without mutating process state, so
    keys never live in the config file and repeated loads remain isolated."""
    from .paths import resolve_config

    resolved = resolve_config(config_path, cwd=cwd)
    project_env_values, user_env_values = _env_layers(cwd)
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
    if not isinstance(p, dict):
        raise ValueError(f"provider {name!r} in {resolved} must be a mapping")
    protocol = p.get("protocol", "auto")
    if protocol not in {"auto", "openai_compat"}:
        raise ValueError(
            f"provider {name!r} in {resolved} has unsupported protocol {protocol!r}; "
            "use auto or openai_compat"
        )
    tiers = p.get("tiers")
    if not isinstance(tiers, dict) or set(tiers) != {"fast", "balanced", "reasoning"}:
        raise ValueError(
            f"provider {name!r} in {resolved} must define exactly "
            "fast, balanced and reasoning tiers"
        )
    if any(not isinstance(model, str) or not model.strip() for model in tiers.values()):
        raise ValueError(f"provider {name!r} in {resolved} has invalid model ids")
    params = p.get("params", {}) or {}
    if not isinstance(params, dict):
        raise ValueError(
            f"provider {name!r} in {resolved} has invalid `params`; expected a mapping"
        )
    unknown_param_tiers = set(params) - set(tiers)
    if unknown_param_tiers:
        raise ValueError(
            f"provider {name!r} in {resolved} has params for unknown tier(s): "
            f"{sorted(unknown_param_tiers)}"
        )
    if any(not isinstance(value, dict) for value in params.values()):
        raise ValueError(f"provider {name!r} in {resolved} has non-mapping tier params")
    api_key_name = p.get("api_key_env", "")
    # Real process values win; project values win over user values, including
    # across repeated provider loads in one embedded process.
    api_key = os.environ.get(api_key_name, "") or project_env_values.get(api_key_name, "")
    if not api_key:
        api_key = user_env_values.get(api_key_name, "")
    api_key_file = str(p.get("api_key_file", "") or "")
    if not api_key and api_key_file:
        key_path = Path(api_key_file).expanduser()
        try:
            api_key = key_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(
                f"provider {name!r} api_key_file {str(key_path)!r} cannot be read: {exc}"
            ) from exc
    # Publish the optional `tools:` block process-wide (ADR 0016): every
    # executing surface passes through here before any tool runs.
    from .toolconfig import configure_tools, parse_tools_block

    configure_tools(parse_tools_block(cfg))
    return ProviderConfig(
        name=name,
        tiers=tiers,
        protocol=protocol,
        api_key=api_key,
        api_key_env=p.get("api_key_env", ""),
        api_key_file=api_key_file,
        base_url=p.get("base_url"),
        judge=p.get("judge"),
        params=params,
    )
