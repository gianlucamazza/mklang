"""Registry resilience: broken stdlib files and entry-point machine plugins."""

import logging
import types

import pytest

import mklang.registry as registry_mod
from mklang.registry import load_entry_point_machines, load_stdlib_registry

MACHINE_DOC = {
    "machine": "plugged",
    "entry": "a",
    "budget": 2,
    "states": {
        "a": {
            "structure": "x",
            "prompt": "p",
            "output": "out",
            "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
        }
    },
}


class _EP:
    def __init__(self, name, obj):
        self.name = name
        self._obj = obj

    def load(self):
        if isinstance(self._obj, Exception):
            raise self._obj
        return self._obj


def _with_eps(monkeypatch, eps):
    fake = types.SimpleNamespace(select=lambda group: eps)
    monkeypatch.setattr(registry_mod, "entry_points", lambda: fake)


@pytest.fixture()
def fresh_stdlib_cache():
    """The stdlib registry is lru_cached; tests that repoint it must not leak."""
    load_stdlib_registry.cache_clear()
    yield
    load_stdlib_registry.cache_clear()


def test_entry_point_machine_document_and_factory(monkeypatch):
    _with_eps(monkeypatch, [_EP("doc", MACHINE_DOC), _EP("factory", lambda: MACHINE_DOC)])
    reg = load_entry_point_machines()
    assert set(reg) == {"plugged"}
    assert reg["plugged"].entry == "a"


def test_entry_point_machine_can_be_blocked_by_allowlist(monkeypatch):
    _with_eps(monkeypatch, [_EP("blocked", MACHINE_DOC)])
    monkeypatch.setenv("MKLANG_ALLOWED_PLUGINS", "other")
    assert load_entry_point_machines() == {}


def test_broken_entry_point_machine_is_skipped_with_warning(monkeypatch, caplog):
    _with_eps(
        monkeypatch,
        [
            _EP("boom", RuntimeError("import explodes")),
            _EP("notdict", "just a string"),
            _EP("good", MACHINE_DOC),
        ],
    )
    with caplog.at_level(logging.WARNING, logger="mklang.registry"):
        reg = load_entry_point_machines()
    assert set(reg) == {"plugged"}  # broken plugins never sink the CLI
    assert sum("failed to load" in r.message for r in caplog.records) == 2


def test_unreadable_entry_points_yield_empty_registry(monkeypatch, caplog):
    def boom():
        raise OSError("metadata unreadable")

    monkeypatch.setattr(registry_mod, "entry_points", boom)
    with caplog.at_level(logging.WARNING, logger="mklang.registry"):
        assert load_entry_point_machines() == {}
    assert any("could not read entry points" in r.message for r in caplog.records)


def test_broken_stdlib_file_is_skipped_with_warning(
    monkeypatch, tmp_path, caplog, fresh_stdlib_cache
):
    (tmp_path / "std_ok.mkl").write_text(
        "machine: std_ok\nentry: a\nbudget: 2\nstates:\n"
        "  a:\n    structure: x\n    prompt: p\n    output: out\n"
        "    gates:\n      - {when: otherwise, then: ok, to: END}\n",
        encoding="utf-8",
    )
    (tmp_path / "std_broken.mkl").write_text("machine: [not a document", encoding="utf-8")

    class _Pkg:
        def joinpath(self, _rel):
            return tmp_path  # a Path satisfies the Traversable surface used here

    monkeypatch.setattr("importlib.resources.files", lambda pkg: _Pkg())
    with caplog.at_level(logging.WARNING, logger="mklang.registry"):
        reg = load_stdlib_registry()
    assert set(reg) == {"std_ok"}  # the broken file is skipped, not fatal
    assert any("std_broken.mkl" in r.message for r in caplog.records)


def test_stdlib_falls_back_to_repo_tree_when_package_copy_is_missing(
    monkeypatch, fresh_stdlib_cache
):
    def raising_files(pkg):
        raise FileNotFoundError("no package data")

    monkeypatch.setattr("importlib.resources.files", raising_files)
    reg = load_stdlib_registry()
    assert "std_cot" in reg  # loaded from the checkout tree fallback
