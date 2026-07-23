"""fs data tools (ADR 0024): tiers, confinement, caps, write gate, atomicity."""

import json
import os
import stat

import pytest

from mklang.fs import (
    MAX_LIST_ENTRIES,
    LocalFSBackend,
    allow_writes,
    configure_fs,
    list_files,
    read_file,
    write_file,
)


def J(s: str) -> dict:
    out = json.loads(s)
    assert isinstance(out, dict)
    return out


# -- stub tier (suite default via conftest MKLANG_FS_BACKEND=stub) -----------


def test_stub_default_is_honest_refusal():
    for fn, tool in ((list_files, "list_files"), (read_file, "read_file")):
        obs = J(fn({"path": "notes"}))
        assert obs["tool"] == tool
        assert obs["stub"] is True
        assert "MKLANG_FS" in obs["error"]
    w = J(write_file({"path": "a.txt", "content": "x"}))
    assert w["stub"] is True and w["written"] is False and w["error"]


# -- local tier --------------------------------------------------------------


@pytest.fixture()
def local_root(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.md").write_text("# b\n", encoding="utf-8")
    (tmp_path / ".hidden").write_text("secret", encoding="utf-8")
    configure_fs(LocalFSBackend(tmp_path))
    return tmp_path


def test_local_list_kinds_and_dotfiles_omitted(local_root):
    obs = J(list_files({}))
    assert obs["stub"] is False and obs["error"] is None
    assert [(e["name"], e["kind"]) for e in obs["entries"]] == [("b.md", "file"), ("docs", "dir")]
    assert obs["count"] == 2 and obs["truncated"] is False
    sub = J(list_files({"path": "docs"}))
    assert sub["entries"] == [{"name": "a.txt", "kind": "file", "bytes": 5}]
    missing = J(list_files({"path": "nope"}))
    assert missing["error"] and missing["entries"] == []


def test_local_list_truncation(tmp_path):
    for i in range(MAX_LIST_ENTRIES + 5):
        (tmp_path / f"f{i:04d}.txt").write_text("x", encoding="utf-8")
    configure_fs(LocalFSBackend(tmp_path))
    obs = J(list_files({}))
    assert obs["count"] == MAX_LIST_ENTRIES + 5
    assert len(obs["entries"]) == MAX_LIST_ENTRIES
    assert obs["truncated"] is True


def test_local_read_exact_and_capped(local_root):
    obs = J(read_file({"path": "docs/a.txt"}))
    assert obs["content"] == "alpha" and obs["bytes"] == 5 and obs["truncated"] is False
    capped = J(read_file({"path": "docs/a.txt", "max_bytes": 2}))
    assert capped["content"] == "al" and capped["bytes"] == 5 and capped["truncated"] is True
    bad = J(read_file({"path": "docs/a.txt", "max_bytes": "many"}))
    assert bad["error"] == "max_bytes must be an integer"
    missing = J(read_file({"path": "docs/nope.txt"}))
    assert missing["error"] and missing["content"] == ""


@pytest.mark.parametrize(
    "path",
    ["../x", "a/../../x", "/etc/passwd", "C:\\evil.txt", "", ".env", ".git/config"],
)
def test_escapes_rejected_never_raise(local_root, path):
    allow_writes(True)
    for fn in (read_file, write_file):
        obs = J(fn({"path": path, "content": "x"}))
        assert obs["error"]


def test_symlink_to_workspace_dotfile_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    try:
        os.symlink(root / ".env", root / "link.md")
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks unavailable")
    configure_fs(LocalFSBackend(root))
    obs = J(read_file({"path": "link.md"}))
    assert obs["error"] and obs["content"] == ""
    listing = J(list_files({}))
    assert [e["name"] for e in listing["entries"]] == []  # link hidden from listing too


def test_list_omits_symlinks_that_leave_the_workspace(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("ok", encoding="utf-8")
    try:
        os.symlink(outside, root / "leak.txt")
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks unavailable")
    configure_fs(LocalFSBackend(root))
    obs = J(list_files({}))
    assert [e["name"] for e in obs["entries"]] == ["a.txt"]


def test_concurrent_writes_to_same_target_do_not_collide(tmp_path):
    import threading

    configure_fs(LocalFSBackend(tmp_path))
    allow_writes(True)
    results = []

    def worker(i):
        results.append(J(write_file({"path": "r.md", "content": f"v{i}", "overwrite": True})))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r["written"] is True and r["error"] is None for r in results)
    assert (tmp_path / "r.md").read_text(encoding="utf-8").startswith("v")
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "r.md"]
    assert leftovers == []


def test_symlink_escape_refused(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    try:
        os.symlink(outside, root / "link.txt")
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks unavailable")
    configure_fs(LocalFSBackend(root))
    obs = J(read_file({"path": "link.txt"}))
    assert obs["error"] and "escapes" in obs["error"]
    allow_writes(True)
    w = J(write_file({"path": "link.txt", "content": "x", "overwrite": True}))
    assert w["written"] is False and "escapes" in w["error"]
    assert outside.read_text(encoding="utf-8") == "secret"


# -- write gate and semantics -------------------------------------------------


def test_local_write_requires_grant(local_root):
    denied = J(write_file({"path": "out/r.md", "content": "x"}))
    assert denied["written"] is False and "allow-write" in denied["error"]
    assert not (local_root / "out").exists()
    allow_writes(True)
    ok = J(write_file({"path": "out/sub/r.md", "content": "hello"}))
    assert ok["written"] is True and ok["stub"] is False
    target = local_root / "out" / "sub" / "r.md"
    assert target.read_text(encoding="utf-8") == "hello"
    leftovers = [p.name for p in target.parent.iterdir() if p.name != "r.md"]
    assert leftovers == []


def test_local_write_overwrite_policy(local_root):
    allow_writes(True)
    first = J(write_file({"path": "out/report.md", "content": "v1"}))
    assert first["written"] is True and first["existed"] is False and first["bytes"] == 2
    assert J(read_file({"path": "out/report.md"}))["content"] == "v1"
    again = J(write_file({"path": "out/report.md", "content": "v2"}))
    assert again["written"] is False and "overwrite" in again["error"]
    forced = J(write_file({"path": "out/report.md", "content": "v2", "overwrite": "true"}))
    assert forced["written"] is True and forced["existed"] is True
    assert J(read_file({"path": "out/report.md"}))["content"] == "v2"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_local_write_mode_0600(local_root):
    allow_writes(True)
    J(write_file({"path": "r.md", "content": "x"}))
    assert stat.S_IMODE((local_root / "r.md").stat().st_mode) == 0o600


def test_local_write_env_grant(local_root, monkeypatch):
    monkeypatch.setenv("MKLANG_FS_WRITE", "1")
    ok = J(write_file({"path": "r.md", "content": "x"}))
    assert ok["written"] is True


def test_write_suffix_allowlist_and_cap(tmp_path):
    configure_fs(LocalFSBackend(tmp_path, max_write_bytes=4))
    allow_writes(True)
    for path in ("run.py", "m.mkl", "noext"):
        obs = J(write_file({"path": path, "content": "x"}))
        assert obs["written"] is False and "not writable" in obs["error"]
    over = J(write_file({"path": "big.txt", "content": "12345"}))
    assert over["written"] is False and "write cap" in over["error"]
    missing = J(write_file({"path": "a.txt"}))
    assert missing["error"] == "missing content"


# -- tier selection ------------------------------------------------------------


def test_env_root_selects_local(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    monkeypatch.delenv("MKLANG_FS_BACKEND", raising=False)
    monkeypatch.setenv("MKLANG_FS_ROOT", str(tmp_path))
    obs = J(read_file({"path": "a.txt"}))
    assert obs["stub"] is False and obs["content"] == "hi"


def test_default_workspace_is_cwd(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("cwd", encoding="utf-8")
    monkeypatch.delenv("MKLANG_FS_BACKEND", raising=False)
    monkeypatch.delenv("MKLANG_FS_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    obs = J(read_file({"path": "a.txt"}))
    assert obs["stub"] is False and obs["content"] == "cwd"


def test_backend_env_stub_wins_over_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MKLANG_FS_ROOT", str(tmp_path))
    for name in ("stub", "off", "unknown-tier"):
        monkeypatch.setenv("MKLANG_FS_BACKEND", name)
        obs = J(list_files({}))
        assert obs["stub"] is True and obs["error"]


def test_configure_fs_overrides_env(tmp_path):
    # conftest pins MKLANG_FS_BACKEND=stub; an explicit binding must win.
    (tmp_path / "a.txt").write_text("live", encoding="utf-8")
    configure_fs(LocalFSBackend(tmp_path))
    assert J(read_file({"path": "a.txt"}))["content"] == "live"


# -- envelope parity ------------------------------------------------------------


def test_payload_keys_match_across_tiers(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "todo.md").write_text("# TODO\n", encoding="utf-8")
    allow_writes(True)
    calls = (
        (list_files, {"path": "notes"}),
        (read_file, {"path": "notes/todo.md"}),
        (write_file, {"path": "out.md", "content": "x"}),
    )
    keysets = []
    for backend in (None, LocalFSBackend(tmp_path)):
        configure_fs(backend)  # None → env tier (stub via conftest)
        keysets.append([sorted(J(fn(dict(inp)))) for fn, inp in calls])
    assert keysets[0] == keysets[1]
