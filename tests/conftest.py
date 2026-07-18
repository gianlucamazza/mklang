"""Shared fixtures for the suite."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def fake_provider_key(monkeypatch):
    """Give mocked-LLM tests a placeholder key so the upfront key gate stays quiet.

    Live tests manage real keys themselves (MKLANG_LIVE=1), and key-gate tests
    delete the variable explicitly to exercise the missing-key path.
    """
    if os.environ.get("MKLANG_LIVE") != "1" and not os.environ.get("DEEPSEEK_API_KEY"):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-not-a-real-key")
