"""Shared fixtures for the suite."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_host_layers(monkeypatch, tmp_path_factory):
    """Keep the suite hermetic against a real mklang installation on the host.

    A pacman/AUR install ships /etc/mklang + /usr/share/mklang, and `mklang
    init --user` creates ~/.config/mklang — all of which would leak into
    config/machine discovery. CI runners are clean, so only dev machines see
    the difference. Tests that need a specific layer re-point these env vars
    or constants themselves.
    """
    from mklang import paths

    sandbox = tmp_path_factory.mktemp("host-layers")
    monkeypatch.setattr(paths, "SYSTEM_CONFIG", sandbox / "etc" / "runtime.yaml")
    monkeypatch.setattr(paths, "SYSTEM_MACHINES", sandbox / "share" / "machines")
    monkeypatch.setenv("MKLANG_CONFIG_DIR", str(sandbox / "user-config"))
    monkeypatch.setenv("MKLANG_DATA_DIR", str(sandbox / "user-data"))
    monkeypatch.setenv("MKLANG_STATE_DIR", str(sandbox / "user-state"))


@pytest.fixture(autouse=True)
def offline_fs(monkeypatch):
    """Keep the suite hermetic: fs tools default to stub unless a test opts in.

    Tests exercising local disk bind LocalFSBackend(tmp_path) via configure_fs
    (which wins over the env tier) and reset it here on teardown.
    """
    from mklang import fs, toolconfig

    monkeypatch.setenv("MKLANG_FS_BACKEND", "stub")
    yield
    fs.configure_fs(None)
    fs.allow_writes(None)
    # load_provider publishes any `tools:` block process-wide; never let one
    # test's config leak into the next.
    toolconfig.configure_tools(None)


@pytest.fixture(autouse=True)
def fake_provider_key(monkeypatch):
    """Give mocked-LLM tests a placeholder key so the upfront key gate stays quiet.

    Live tests manage real keys themselves (MKLANG_LIVE=1), and key-gate tests
    delete the variable explicitly to exercise the missing-key path.
    """
    if os.environ.get("MKLANG_LIVE") != "1" and not os.environ.get("DEEPSEEK_API_KEY"):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-not-a-real-key")
