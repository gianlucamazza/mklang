"""Tests for the evidence release builder's filesystem and row contract."""

import importlib.util
import json
from pathlib import Path

import pytest
from conftest import REPO_ROOT


def _builder_main():
    path = REPO_ROOT / "scripts" / "build_evidence_release.py"
    spec = importlib.util.spec_from_file_location("build_evidence_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _row() -> dict:
    return {
        "schema_version": "1.0",
        "runtime_version": "1.3.1",
        "spec_version": "0.4",
        "experiment": "gate-divergence",
        "provider": "fixture",
        "model": "fixture-model",
        "started_at": "2026-08-30T00:00:00Z",
        "judge_model": None,
        "judge_tier": None,
        "provider_params": {},
        "machine": "fixture",
        "variant": "base",
        "repeat": 0,
        "status": "done",
        "input_hash": "a" * 64,
        "output_hash": "b" * 12,
        "route": "fixture>END",
        "signature": "fixture|0|otherwise|END",
    }


def _release(path: Path):
    (path / "environments.json").write_text("{}\n", encoding="utf-8")
    (path / "summary.json").write_text("{}\n", encoding="utf-8")
    (path / "REPORT.md").write_text("# Fixture\n", encoding="utf-8")
    (path / "runs.jsonl").write_text(json.dumps(_row()) + "\n", encoding="utf-8")


def test_builder_requires_release_metadata(tmp_path, monkeypatch):
    main = _builder_main()
    monkeypatch.setattr("sys.argv", ["build_evidence_release.py", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_builder_writes_manifest_for_valid_release(tmp_path, monkeypatch):
    main = _builder_main()
    _release(tmp_path)
    monkeypatch.setattr("sys.argv", ["build_evidence_release.py", str(tmp_path)])
    assert main() == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["rows"] == 1
    assert set(manifest["files"]) == {
        "REPORT.md",
        "environments.json",
        "runs.jsonl",
        "summary.json",
    }


def test_builder_rejects_invalid_json_and_does_not_write_manifest(tmp_path, monkeypatch):
    main = _builder_main()
    _release(tmp_path)
    (tmp_path / "runs.jsonl").write_text("not-json\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["build_evidence_release.py", str(tmp_path)])
    assert main() == 1
    assert not (tmp_path / "manifest.json").exists()
