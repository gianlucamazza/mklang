"""Unit tests for demo asset helpers (no live render)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "demo_assets.py"


@pytest.fixture(scope="module")
def demo_assets():
    spec = importlib.util.spec_from_file_location("demo_assets", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_normalize_transcript_collapses_typing_frames(demo_assets) -> None:
    raw = [
        "> PYTHONPATH=src python -m mklang.cli c",
        "> PYTHONPATH=src python -m mklang.cli check examples/react.mkl",
        "OK examples/react.mkl",
        "────────────────",
        ">",
        "DONE react · provider deepseek",
        "│ 153                                                                          │",
        "tokens 100+20 · steps 6",
    ]
    cleaned = demo_assets._normalize_transcript_lines(raw)
    assert cleaned == [
        "> PYTHONPATH=src python -m mklang.cli check examples/react.mkl",
        "OK examples/react.mkl",
        "DONE react · provider deepseek",
        "│ 153                                                                          │",
        "tokens 100+20 · steps 6",
    ]


def test_normalize_transcript_keeps_distinct_prose(demo_assets) -> None:
    raw = [
        "│  Open-source models advanced this week.                                      │",
        "│  Open-source models advanced this week. More detail.                         │",
    ]
    cleaned = demo_assets._normalize_transcript_lines(raw)
    # Prose lines are not treated as typing prefixes (no > / python).
    assert len(cleaned) == 2
