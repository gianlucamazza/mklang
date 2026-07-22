"""The runtime.yaml `tools:` block (ADR 0016): precedence, plumbing, doctor."""

import json

import yaml

from mklang import cli, config, fs, kb, mail, search, toolconfig

MINIMAL = {
    "active": "local",
    "providers": {"local": {"tiers": {"fast": "m", "balanced": "m", "reasoning": "m"}}},
}


def _load(tmp_path, tools: dict | None):
    cfg = dict(MINIMAL)
    if tools is not None:
        cfg["tools"] = tools
    path = tmp_path / "runtime.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return config.load_provider(path)


def test_without_tools_block_everything_stays_default(tmp_path, monkeypatch):
    _load(tmp_path, None)
    # after _load: load_provider ran load_env_files(), which may have pulled a
    # developer's real keys out of layered .env files — clear them for the test
    monkeypatch.delenv("MKLANG_SEARCH_BACKEND", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("MKLANG_KB_BACKEND", raising=False)
    monkeypatch.delenv("MKLANG_MAIL_BACKEND", raising=False)
    assert search.resolve_backend_name() == ("stub", "default")
    assert kb.resolve_backend_name() == ("stub", "default")
    assert mail.resolve_backend_name() == ("stub", "default")
    assert fs.resolve_backend_name() == ("stub", "env")  # conftest pins the env
    obs = json.loads(search.search({"query": "q"}))
    assert obs["stub"] is True and "no external search bound" in obs["error"]


def test_yaml_binds_backends_over_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MKLANG_SEARCH_BACKEND", raising=False)
    monkeypatch.delenv("MKLANG_KB_BACKEND", raising=False)
    _load(tmp_path, {"search": {"backend": "fake"}, "kb": {"backend": "fake"}})
    assert search.resolve_backend_name() == ("fake", "config")
    assert kb.resolve_backend_name() == ("fake", "config")
    obs = json.loads(search.search({"query": "q"}))
    assert obs["results"] and obs["results"][0]["url"] == "https://example.com/"


def test_env_beats_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("MKLANG_SEARCH_BACKEND", "stub")
    _load(tmp_path, {"search": {"backend": "fake"}})
    assert search.resolve_backend_name() == ("stub", "env")


def test_yaml_stub_beats_tavily_autoselect(tmp_path, monkeypatch):
    monkeypatch.delenv("MKLANG_SEARCH_BACKEND", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    _load(tmp_path, {"search": {"backend": "stub"}})
    assert search.resolve_backend_name() == ("stub", "config")


def test_fs_backend_and_workspace_from_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("MKLANG_FS_BACKEND", raising=False)
    monkeypatch.delenv("MKLANG_FS_ROOT", raising=False)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "data.txt").write_text("hi", encoding="utf-8")
    _load(tmp_path, {"fs": {"backend": "local", "workspace": str(ws)}})
    assert fs.resolve_backend_name() == ("local", "config")
    assert fs.resolve_workspace_with_source() == (ws, "config")
    obs = json.loads(fs.read_file({"path": "data.txt"}))
    assert obs["stub"] is False and obs["content"] == "hi"


def test_fs_write_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("MKLANG_FS_WRITE", raising=False)
    _load(tmp_path, {"fs": {"write": True}})
    assert fs.writes_allowed_with_source() == (True, "config")
    # a SET falsy env var is an explicit off that beats the config grant
    monkeypatch.setenv("MKLANG_FS_WRITE", "0")
    assert fs.writes_allowed_with_source() == (False, "env")
    # the runtime grant (--allow-write / console consent) beats everything
    fs.allow_writes(True)
    assert fs.writes_allowed_with_source() == (True, "runtime")


def test_configure_still_outranks_env_and_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("MKLANG_SEARCH_BACKEND", "stub")
    _load(tmp_path, {"search": {"backend": "stub"}})
    rows = [{"title": "T", "url": "https://t.example", "snippet": "s"}]
    search.configure_search(search.FakeSearchBackend(rows))
    try:
        obs = json.loads(search.search({"query": "q"}))
        assert obs["results"][0]["url"] == "https://t.example"
    finally:
        search.configure_search(None)


def test_junk_tools_block_never_crashes_load(tmp_path):
    prov = _load(tmp_path, {"search": "not-a-dict", "fs": {"write": "yes"}, "junk": 3})
    assert prov.name == "local"
    assert toolconfig.current_tools() == toolconfig.EMPTY or isinstance(
        toolconfig.current_tools(), toolconfig.ToolsConfig
    )


def test_doctor_reports_config_source_and_schema_warning(tmp_path, monkeypatch, capsys):
    from test_first_run import _doctor_host

    _doctor_host(tmp_path, monkeypatch)
    monkeypatch.delenv("MKLANG_SEARCH_BACKEND", raising=False)
    cfg_path = tmp_path / "runtime.yaml"
    cfg = dict(MINIMAL)
    cfg["tools"] = {"search": {"backend": "fake", "api_key": "nope"}}
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    assert cli.main(["doctor", "--config", str(cfg_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    names = [i["name"] for i in payload["items"]]
    assert any(n == "tools search · backend=fake · source=config" for n in names)
    schema_items = [i for i in payload["items"] if i["name"].startswith("schema ")]
    assert schema_items and any("api_key" in w for w in schema_items[0]["warnings"])
