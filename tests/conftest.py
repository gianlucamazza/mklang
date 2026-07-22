"""Shared fixtures for the suite."""

from __future__ import annotations

import os

import pytest


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
