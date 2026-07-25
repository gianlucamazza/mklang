"""Malformed sibling machines remain non-blocking but observable."""

from mklang.registry import load_registry


def test_load_registry_warns_when_sibling_is_skipped(tmp_path, caplog):
    (tmp_path / "broken.mkl").write_text("machine: [broken", encoding="utf-8")
    with caplog.at_level("WARNING", logger="mklang.registry"):
        assert load_registry(tmp_path) == {}
    assert "broken.mkl" in caplog.text
