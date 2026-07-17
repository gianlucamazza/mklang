"""ADR 0021 host paths, config discovery, init, and machine layering."""

from __future__ import annotations

import json

from mklang import cli
from mklang.paths import host_paths, resolve_config
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
