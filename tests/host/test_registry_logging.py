"""Malformed sibling machines remain non-blocking but observable."""

from mklang.registry import load_registry


def test_load_registry_warns_when_sibling_is_skipped(tmp_path, caplog):
    (tmp_path / "broken.mkl").write_text("machine: [broken", encoding="utf-8")
    with caplog.at_level("WARNING", logger="mklang.registry"):
        assert load_registry(tmp_path) == {}
    assert "broken.mkl" in caplog.text


def test_load_registry_rejects_symlink_outside_root(tmp_path, caplog):
    outside = tmp_path / "outside.mkl"
    outside.write_text(
        "machine: outside\nentry: s\nstates: {s: {prompt: x, output: y, gates: [{when: otherwise, to: END} ]}}\n",
        encoding="utf-8",
    )
    root = tmp_path / "machines"
    root.mkdir()
    (root / "link.mkl").symlink_to(outside)
    with caplog.at_level("WARNING", logger="mklang.registry"):
        assert load_registry(root) == {}
    assert "symlink escapes" in caplog.text
