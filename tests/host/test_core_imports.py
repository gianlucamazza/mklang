"""Core parse/check/lint/scripted-test imports stay free of CLI/TUI/provider SDKs."""

from __future__ import annotations

import subprocess
import sys


def test_core_import_does_not_pull_openai_textual_rich() -> None:
    """A clean interpreter loading the offline host path must not import SDKs.

    openai / textual / rich are CLI, TUI, and live-provider dependencies.
    Parse, schema check, lint, and scripted runs do not need them — that is
    what lets Gradio-Lite install the wheel with ``deps=False``.
    """
    script = r"""
import sys

from mklang.host import check_machine
from mklang.lint import lint_machine
from mklang.loader import validate_dict
from mklang.model import parse_machine
from mklang.scripttest import match_expectation, run_scenario

forbidden = ("openai", "textual", "rich")
loaded = [
    name
    for name in forbidden
    if name in sys.modules or any(mod.startswith(name + ".") for mod in sys.modules)
]
assert not loaded, f"core import pulled {loaded}"
# Provider .env loading is lazy too (python-dotenv is not a parse/lint dep).
assert "dotenv" not in sys.modules
assert check_machine and lint_machine and validate_dict
assert parse_machine and match_expectation and run_scenario
"""
    subprocess.run([sys.executable, "-c", script], check=True)
