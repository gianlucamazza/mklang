"""Host filesystem layout and discovery (ADR 0021 phases 1-2)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path


@dataclass(frozen=True)
class HostPaths:
    config: Path
    data: Path
    state: Path

    @property
    def user_config(self) -> Path:
        return self.config / "runtime.yaml"

    @property
    def user_env(self) -> Path:
        return self.config / ".env"

    @property
    def user_machines(self) -> Path:
        return self.data / "machines"

    @property
    def sessions(self) -> Path:
        return self.state / "console" / "sessions"

    @property
    def checkpoints(self) -> Path:
        return self.state / "checkpoints"


def host_paths() -> HostPaths:
    home = Path.home()
    return HostPaths(
        config=Path(
            os.environ.get(
                "MKLANG_CONFIG_DIR",
                os.environ.get("XDG_CONFIG_HOME", str(home / ".config")) + "/mklang",
            )
        ).expanduser(),
        data=Path(
            os.environ.get(
                "MKLANG_DATA_DIR",
                os.environ.get("XDG_DATA_HOME", str(home / ".local/share")) + "/mklang",
            )
        ).expanduser(),
        state=Path(
            os.environ.get(
                "MKLANG_STATE_DIR",
                os.environ.get("XDG_STATE_HOME", str(home / ".local/state")) + "/mklang",
            )
        ).expanduser(),
    )


def bundled_config() -> Path:
    """Return the installed example config, or its checkout source."""
    packaged = files("mklang").joinpath("data/runtime.example.yaml")
    if packaged.is_file():
        return Path(str(packaged))
    checkout = Path(__file__).resolve().parents[2] / "config" / "runtime.example.yaml"
    if checkout.is_file():
        return checkout
    raise FileNotFoundError("the bundled runtime example is missing from this installation")


def bundled_config_schema() -> Path:
    packaged = files("mklang").joinpath("data/runtime.schema.json")
    if packaged.is_file():
        return Path(str(packaged))
    return Path(__file__).resolve().parents[2] / "config" / "runtime.schema.json"


def bundled_env_example() -> Path:
    packaged = files("mklang").joinpath("data/env.example")
    if packaged.is_file():
        return Path(str(packaged))
    return Path(__file__).resolve().parents[2] / ".env.example"


def bundled_sample_machine() -> Path:
    """The hello-world machine `mklang init` scaffolds into machines/."""
    packaged = files("mklang").joinpath("data/init/hello.mk")
    if packaged.is_file():
        return Path(str(packaged))
    raise FileNotFoundError("the bundled sample machine is missing from this installation")


def bundled_sample_test() -> Path:
    """The scripted scenarios for the scaffolded sample machine (keyless first run)."""
    packaged = files("mklang").joinpath("data/init/hello.test.yaml")
    if packaged.is_file():
        return Path(str(packaged))
    raise FileNotFoundError("the bundled sample test script is missing from this installation")


def resolve_config(explicit: str | Path | None = None, *, cwd: Path | None = None) -> Path:
    """Resolve runtime config using ADR 0021's stable precedence order."""
    return resolve_config_with_layer(explicit, cwd=cwd)[0]


def resolve_config_with_layer(
    explicit: str | Path | None = None, *, cwd: Path | None = None
) -> tuple[Path, str]:
    """Like resolve_config, but also name the layer that won.

    Layers: explicit > env > project (local) > user (global) > system > bundled."""
    if explicit:
        return Path(explicit).expanduser(), "explicit"
    env = os.environ.get("MKLANG_CONFIG")
    if env:
        return Path(env).expanduser(), "env"
    here = cwd or Path.cwd()
    for candidate, layer in (
        (here / "config" / "runtime.yaml", "project"),
        (host_paths().user_config, "user"),
        (Path("/etc/mklang/runtime.yaml"), "system"),
    ):
        if candidate.is_file():
            return candidate, layer
    # Preserve the checkout experience while also working from an installed wheel.
    checkout_example = here / "config" / "runtime.example.yaml"
    if checkout_example.is_file():
        return checkout_example, "bundled"
    return bundled_config(), "bundled"


def machine_layers() -> list[tuple[str, Path]]:
    """System then user machine roots; later layers have higher precedence."""
    return [
        ("system", Path("/usr/share/mklang/machines")),
        ("user", host_paths().user_machines),
    ]
