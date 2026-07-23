"""Human/automation CLI output contracts (ADR 0022)."""

from __future__ import annotations

import json

from mklang import cli


def test_check_json_has_stable_envelope(capsys):
    rc = cli.main(["check", "examples/triage.mkl", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["command"] == "check" and payload["ok"] is True
    assert payload["items"][0]["path"] == "examples/triage.mkl"


def test_machines_auto_keeps_json_when_stdout_is_not_a_tty(capsys):
    assert cli.main(["machines"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(row["name"] == "std_cot" for row in payload)


def test_invalid_set_is_a_clean_diagnostic(monkeypatch, capsys):
    from mklang.llm.mock import MockLLM

    monkeypatch.setattr(cli, "_build_llm", lambda provider: MockLLM())
    rc = cli.main(["run", "std_cot", "--set", "broken", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2 and payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "invalid-input"


def test_run_workspace_flags_bind_the_fs_tools(tmp_path, monkeypatch, capsys):
    from mklang import fs
    from mklang.llm.mock import MockLLM

    monkeypatch.setattr(cli, "_build_llm", lambda provider: MockLLM())
    rc = cli.main(["run", "std_cot", "--workspace", str(tmp_path / "nope"), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2 and payload["diagnostics"][0]["code"] == "invalid-input"

    rc = cli.main(
        [
            "run",
            "std_cot",
            "--set",
            "task=hi",
            "--workspace",
            str(tmp_path),
            "--allow-write",
            "--format",
            "json",
        ]
    )
    capsys.readouterr()
    assert rc == 0
    backend = fs.current_fs_backend()
    assert isinstance(backend, fs.LocalFSBackend) and backend.root == tmp_path.resolve()
    assert fs.writes_allowed() is True


def test_missing_console_session_does_not_dump_traceback(tmp_path, monkeypatch, capsys):
    import pytest

    pytest.importorskip("textual")
    monkeypatch.setenv("MKLANG_STATE_DIR", str(tmp_path / "state"))
    rc = cli.main(["console", "--session", "missing", "--workspace", str(tmp_path / "machines")])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in captured.out + captured.err
    assert "state.json" in captured.out + captured.err
