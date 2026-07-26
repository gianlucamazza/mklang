"""First-run experience: --version, bare invocation, init scaffolding, key gate."""

from __future__ import annotations

import json
import os

import pytest

import mklang
from mklang import cli, host
from mklang.config import ProviderConfig


CONFIG = "config/runtime.example.yaml"


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert f"mklang {mklang.__version__}" in capsys.readouterr().out


def test_bare_invocation_is_a_nudge(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "mklang init" in out and "console" in out
    assert "usage:" not in out


def test_unknown_subcommand_still_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["bogus"])
    assert exc.value.code == 2


def test_init_scaffolds_project_with_sample(tmp_path, capsys):
    target = tmp_path / "project"
    assert cli.main(["init", "--dir", str(target), "--format", "json"]) == 0
    first = json.loads(capsys.readouterr().out)
    names = {item["name"]: item["status"] for item in first["items"]}
    assert names[str(target / "machines" / "hello.mkl")] == "ok"
    assert names[str(target / "machines" / "hello.test.yaml")] == "ok"
    sample = (target / "machines" / "hello.mkl").read_text(encoding="utf-8")

    assert cli.main(["init", "--dir", str(target), "--format", "json"]) == 0
    second = json.loads(capsys.readouterr().out)
    names = {item["name"]: item["status"] for item in second["items"]}
    assert names[str(target / "machines" / "hello.mkl")] == "exists"
    assert (target / "machines" / "hello.mkl").read_text(encoding="utf-8") == sample


def test_init_user_mode_scaffolds_sample(tmp_path, monkeypatch, capsys):
    # This test pins XDG resolution itself: drop the suite-wide MKLANG_*_DIR
    # sandbox (conftest isolated_host_layers), which would take precedence.
    for var in ("MKLANG_CONFIG_DIR", "MKLANG_DATA_DIR", "MKLANG_STATE_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert cli.main(["init", "--user", "--format", "json"]) == 0
    capsys.readouterr()
    assert (tmp_path / "data" / "mklang" / "machines" / "hello.mkl").is_file()
    assert (tmp_path / "data" / "mklang" / "machines" / "hello.test.yaml").is_file()
    # The schema lands next to runtime.yaml so its yaml-language-server
    # header validates in the user host too.
    assert (tmp_path / "config" / "mklang" / "runtime.schema.json").is_file()


def test_init_sample_passes_its_own_scenarios(tmp_path, capsys):
    target = tmp_path / "project"
    assert cli.main(["init", "--dir", str(target)]) == 0
    capsys.readouterr()
    machine = str(target / "machines" / "hello.mkl")
    script = str(target / "machines" / "hello.test.yaml")
    assert cli.main(["test", machine, "--script", script, "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["summary"]["failed"] == 0


def _no_key(monkeypatch, tmp_path):
    """A cwd with no .env, no user-host .env, and no key in the environment."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    # Point the user host at an empty dir so the host machine's real
    # ~/.config/mklang/.env can never leak into the gate under test.
    monkeypatch.setenv("MKLANG_CONFIG_DIR", str(tmp_path / "no-user-config"))
    monkeypatch.chdir(tmp_path)


def test_missing_key_fails_fast(tmp_path, monkeypatch, capsys):
    _no_key(monkeypatch, tmp_path)
    from mklang.paths import bundled_config

    rc = cli.main(["run", "std_cot", "--config", str(bundled_config()), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2 and payload["ok"] is False
    diag = payload["diagnostics"][0]
    assert diag["code"] == "prepare-config"
    assert "DEEPSEEK_API_KEY" in diag["message"] and ".env" in diag["message"]


def test_local_provider_is_exempt_from_the_key_gate():
    prov = ProviderConfig(
        name="local", tiers={"fast": "m"}, api_key="", api_key_env="LOCAL_API_KEY"
    )
    assert host.missing_key_message(prov) is None
    keyed = ProviderConfig(name="openai", tiers={"fast": "m"}, api_key="sk-x")
    assert host.missing_key_message(keyed) is None


def _doctor_host(tmp_path, monkeypatch, key_env="MK_TEST_DOCTOR_KEY"):
    """An isolated user host whose active provider reads key_env."""
    # A throwaway copy of the environment: load_dotenv writes stay test-local.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setenv("MKLANG_CONFIG_DIR", str(tmp_path / "conf"))
    monkeypatch.setenv("MKLANG_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MKLANG_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv(key_env, raising=False)
    conf = tmp_path / "conf"
    conf.mkdir()
    conf.joinpath("runtime.yaml").write_text(
        "active: fake\n"
        "providers:\n"
        "  fake:\n"
        f"    api_key_env: {key_env}\n"
        "    tiers: {fast: m, balanced: m, reasoning: m}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_doctor_flags_the_missing_active_key(tmp_path, monkeypatch, capsys):
    _doctor_host(tmp_path, monkeypatch)
    assert cli.main(["doctor", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and payload["summary"]["layer"] == "user"
    names = [item["name"] for item in payload["items"]]
    assert any(name.startswith("key fake") and "missing" in name for name in names)


def test_doctor_rejects_an_empty_or_invalid_config(tmp_path, monkeypatch, capsys):
    _doctor_host(tmp_path, monkeypatch)
    conf = tmp_path / "conf" / "runtime.yaml"
    conf.write_text("", encoding="utf-8")
    assert cli.main(["doctor", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    conf.write_text("active: ghost\nproviders: {}\n", encoding="utf-8")
    assert cli.main(["doctor", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert any("active" in e for i in payload["items"] for e in i.get("errors", []))


def test_doctor_flags_stale_config_keys_via_the_schema(tmp_path, monkeypatch, capsys):
    _doctor_host(tmp_path, monkeypatch)
    monkeypatch.setenv("MK_TEST_DOCTOR_KEY", "x")
    conf = tmp_path / "conf" / "runtime.yaml"
    # A config seeded from an older example still carrying the removed run: block.
    conf.write_text(conf.read_text(encoding="utf-8") + "run:\n  trace: true\n", encoding="utf-8")
    assert cli.main(["doctor", "--format", "json"]) == 0  # warning, not a failure
    payload = json.loads(capsys.readouterr().out)
    schema_items = [i for i in payload["items"] if i["name"].startswith("schema ")]
    assert schema_items and any("run" in w for w in schema_items[0]["warnings"])


def test_doctor_reports_tool_backends(tmp_path, monkeypatch, capsys):
    _doctor_host(tmp_path, monkeypatch)
    monkeypatch.setenv("MK_TEST_DOCTOR_KEY", "x")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("MKLANG_SEARCH_BACKEND", raising=False)
    assert cli.main(["doctor", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    names = [i["name"] for i in payload["items"]]
    assert any(n == "tools search · backend=stub · source=default" for n in names)
    assert any(n == "tools fs · backend=stub · source=env" for n in names)  # conftest pins stub
    monkeypatch.setenv("MKLANG_SEARCH_BACKEND", "tavily")
    assert cli.main(["doctor", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    tavily = [i for i in payload["items"] if i["name"].startswith("tools search")]
    assert tavily[0]["status"] == "warning"  # tavily forced without its key
    monkeypatch.delenv("MKLANG_FS_BACKEND", raising=False)
    monkeypatch.delenv("MKLANG_FS_ROOT", raising=False)
    monkeypatch.delenv("MKLANG_FS_WRITE", raising=False)
    assert cli.main(["doctor", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    fs_line = [i for i in payload["items"] if i["name"].startswith("tools fs")][0]
    assert fs_line["status"] == "ok"
    assert f"workspace={tmp_path}" in fs_line["name"] and "write=off" in fs_line["name"]
    assert "source=default" in fs_line["name"]


def test_doctor_passes_when_the_active_key_is_set(tmp_path, monkeypatch, capsys):
    _doctor_host(tmp_path, monkeypatch)
    monkeypatch.setenv("MK_TEST_DOCTOR_KEY", "x")
    assert cli.main(["doctor", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["summary"]["active"] == "fake"
    names = [item["name"] for item in payload["items"]]
    assert any(name.startswith("config ") and "layer=user" in name for name in names)
    assert any(name.startswith("state checkpoints") for name in names)


def test_console_missing_key_fails_fast(tmp_path, monkeypatch, capsys):
    pytest.importorskip("textual")
    _no_key(monkeypatch, tmp_path)
    from mklang.paths import bundled_config

    rc = cli.main(["console", "--config", str(bundled_config())])
    captured = capsys.readouterr()
    assert rc == 2
    assert "DEEPSEEK_API_KEY" in captured.err
    assert "Traceback" not in captured.out + captured.err
