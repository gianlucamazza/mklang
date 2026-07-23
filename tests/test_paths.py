"""ADR 0021/0023 host paths, config discovery, env layering, init, machine layering."""

from __future__ import annotations

import json
import os
from pathlib import Path

from mklang import cli
from mklang.config import load_env_files
from mklang.paths import host_paths, resolve_config, resolve_config_with_layer
from mklang.registry import registry_with_sources


def _machine(name: str) -> str:
    return f"""machine: {name}
entry: s
budget: 2
states:
  s:
    structure: answer
    prompt: answer
    output: out
    gates: [{{when: otherwise, then: ok, to: END}}]
"""


def test_xdg_roots_and_config_precedence(tmp_path, monkeypatch):
    # This test pins XDG resolution itself: drop the suite-wide MKLANG_*_DIR
    # sandbox (conftest isolated_host_layers), which would take precedence.
    for var in ("MKLANG_CONFIG_DIR", "MKLANG_DATA_DIR", "MKLANG_STATE_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    paths = host_paths()
    assert paths.user_config == tmp_path / "config" / "mklang" / "runtime.yaml"
    assert paths.user_machines == tmp_path / "data" / "mklang" / "machines"
    assert paths.sessions == tmp_path / "state" / "mklang" / "console" / "sessions"

    paths.user_config.parent.mkdir(parents=True)
    paths.user_config.write_text("active: user\nproviders: {}\n", encoding="utf-8")
    assert resolve_config(cwd=tmp_path) == paths.user_config
    project = tmp_path / "config" / "runtime.yaml"
    project.parent.mkdir(exist_ok=True)
    project.write_text("active: project\nproviders: {}\n", encoding="utf-8")
    assert resolve_config(cwd=tmp_path) == project
    explicit = tmp_path / "custom.yaml"
    assert resolve_config(explicit, cwd=tmp_path) == explicit


def test_init_is_idempotent_and_never_overwrites(tmp_path, capsys):
    target = tmp_path / "project"
    assert cli.main(["init", "--dir", str(target), "--format", "json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["ok"] is True and (target / "config/runtime.yaml").is_file()
    original = (target / "config/runtime.yaml").read_text(encoding="utf-8")
    assert cli.main(["init", "--dir", str(target), "--format", "json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["summary"]["unchanged"] >= 2
    assert (target / "config/runtime.yaml").read_text(encoding="utf-8") == original


def test_resolve_config_names_the_winning_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("MKLANG_CONFIG_DIR", str(tmp_path / "userconf"))
    monkeypatch.delenv("MKLANG_CONFIG", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    assert resolve_config_with_layer(cwd=project)[1] == "bundled"
    user = tmp_path / "userconf"
    user.mkdir()
    (user / "runtime.yaml").write_text("active: u\nproviders: {}\n", encoding="utf-8")
    assert resolve_config_with_layer(cwd=project) == (user / "runtime.yaml", "user")
    (project / "config").mkdir()
    (project / "config" / "runtime.yaml").write_text("active: p\nproviders: {}\n", encoding="utf-8")
    assert resolve_config_with_layer(cwd=project)[1] == "project"
    monkeypatch.setenv("MKLANG_CONFIG", str(user / "runtime.yaml"))
    assert resolve_config_with_layer(cwd=project)[1] == "env"
    assert resolve_config_with_layer("x.yaml", cwd=project)[1] == "explicit"


def test_user_env_fills_gaps_behind_the_project_env(tmp_path, monkeypatch):
    # Layering is per key: the project .env wins where both define a key,
    # the user .env fills what the project one lacks.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setenv("MKLANG_CONFIG_DIR", str(tmp_path / "userconf"))
    userconf = tmp_path / "userconf"
    userconf.mkdir()
    (userconf / ".env").write_text(
        "MK_TEST_SHARED=user\nMK_TEST_USER_ONLY=user\n", encoding="utf-8"
    )
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("MK_TEST_SHARED=project\n", encoding="utf-8")
    monkeypatch.chdir(project)
    for var in ("MK_TEST_SHARED", "MK_TEST_USER_ONLY"):
        monkeypatch.delenv(var, raising=False)
    loaded_project, loaded_user = load_env_files()
    assert loaded_project and loaded_project.endswith(".env")
    assert loaded_user == str(userconf / ".env")
    assert os.environ["MK_TEST_SHARED"] == "project"
    assert os.environ["MK_TEST_USER_ONLY"] == "user"


def test_console_workspace_prefers_local_then_user_machines(tmp_path, monkeypatch):
    monkeypatch.setenv("MKLANG_DATA_DIR", str(tmp_path / "data"))
    cwd = tmp_path / "somewhere"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert cli._resolve_workspace(None) == str(tmp_path / "data" / "machines")
    (cwd / "machines").mkdir()
    assert cli._resolve_workspace(None) == str(Path("./machines"))
    assert cli._resolve_workspace("custom/dir") == "custom/dir"


def test_hitl_default_checkpoint_lands_in_the_state_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MKLANG_STATE_DIR", str(tmp_path / "state"))
    first = cli._default_checkpoint("machines/hello.mk")
    second = cli._default_checkpoint("machines/hello.mk")
    assert first.parent == tmp_path / "state" / "checkpoints"
    assert first.parent.is_dir()
    assert first.name.startswith("hello-") and first.suffix == ".json"
    assert first != second  # unique per invocation


def test_user_machine_precedes_system_and_project_precedes_user(tmp_path, monkeypatch):
    monkeypatch.setenv("MKLANG_DATA_DIR", str(tmp_path / "data"))
    user = tmp_path / "data" / "machines"
    user.mkdir(parents=True)
    (user / "shared.mk").write_text(_machine("shared"), encoding="utf-8")
    reg, sources = registry_with_sources()
    assert "shared" in reg and sources["shared"] == "user"

    project = tmp_path / "project"
    project.mkdir()
    (project / "shared.mk").write_text(_machine("shared"), encoding="utf-8")
    _, sources = registry_with_sources(project)
    assert sources["shared"] == "local"
