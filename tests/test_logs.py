"""Process logging (BP §12): level wiring, idempotent handler, converted warnings."""

import logging

import pytest

from mklang import cli, fs
from mklang.logs import setup_process_logging


@pytest.fixture(autouse=True)
def _clean_level_env(monkeypatch):
    """A developer's shell MKLANG_LOG_LEVEL must not steer these tests."""
    monkeypatch.delenv("MKLANG_LOG_LEVEL", raising=False)
    yield
    # main() retunes the shared logger; leave the suite at the default.
    setup_process_logging(None)


def _mklang_logger():
    return logging.getLogger("mklang")


def test_default_level_is_warning_and_handler_idempotent(capsys):
    cli.main(["machines"])
    cli.main(["machines"])
    logger = _mklang_logger()
    named = [h for h in logger.handlers if h.name == "mklang-process"]
    assert len(named) == 1  # repeated main() calls never stack handlers
    assert logger.getEffectiveLevel() == logging.WARNING


def test_env_sets_level(monkeypatch, capsys):
    monkeypatch.setenv("MKLANG_LOG_LEVEL", "INFO")
    cli.main(["machines"])
    assert _mklang_logger().getEffectiveLevel() == logging.INFO


def test_flag_beats_env(monkeypatch, capsys):
    monkeypatch.setenv("MKLANG_LOG_LEVEL", "warning")
    cli.main(["machines", "--log-level", "debug"])
    assert _mklang_logger().getEffectiveLevel() == logging.DEBUG


def test_invalid_env_falls_back_to_warning(monkeypatch, capsys, caplog):
    monkeypatch.setenv("MKLANG_LOG_LEVEL", "verbose")
    with caplog.at_level(logging.WARNING, logger="mklang.logs"):
        cli.main(["machines"])
    assert _mklang_logger().getEffectiveLevel() == logging.WARNING
    assert any("MKLANG_LOG_LEVEL" in r.message for r in caplog.records)


def test_registry_plugin_warning_is_a_log_record(monkeypatch, capsys, caplog):
    from mklang import registry

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(registry, "entry_points", boom)
    with caplog.at_level(logging.WARNING, logger="mklang.registry"):
        reg = registry.load_entry_point_machines()
    assert reg == {}
    assert any("could not read entry points" in r.message for r in caplog.records)
    # the old stderr print is gone
    assert "# warning:" not in capsys.readouterr().err


def test_fs_audit_visible_at_info(tmp_path, caplog):
    (tmp_path / "data.txt").write_text("hello", encoding="utf-8")
    fs.configure_fs(fs.LocalFSBackend(tmp_path))
    try:
        with caplog.at_level(logging.INFO, logger="mklang.fs"):
            fs.read_file({"path": "data.txt"})
    finally:
        fs.configure_fs(None)
    assert any(r.message.startswith("read_file") for r in caplog.records)
