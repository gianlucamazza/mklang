"""The keyless Space folder stays self-contained and importable offline."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from conftest import REPO_ROOT

SPACE = REPO_ROOT / "spaces" / "playground"
APP = SPACE / "app.py"

# The Space folder is excluded from the PyPI sdist (lean AUR check surface).
needs_space = pytest.mark.skipif(
    not APP.is_file(), reason="spaces/playground not present (sdist build)"
)

BUNDLED = (
    (
        SPACE / "examples" / "hello.mkl",
        REPO_ROOT / "src" / "mklang" / "data" / "init" / "hello.mkl",
    ),
    (
        SPACE / "examples" / "hello.test.yaml",
        REPO_ROOT / "src" / "mklang" / "data" / "init" / "hello.test.yaml",
    ),
    (SPACE / "examples" / "triage.mkl", REPO_ROOT / "examples" / "triage.mkl"),
    (
        SPACE / "examples" / "triage.test.yaml",
        REPO_ROOT / "examples" / "triage.test.yaml",
    ),
    (
        SPACE / "conformance" / "linear.yaml",
        REPO_ROOT / "conformance" / "cases" / "linear.yaml",
    ),
    (
        SPACE / "conformance" / "parse-json.yaml",
        REPO_ROOT / "conformance" / "cases" / "parse-json.yaml",
    ),
    (
        SPACE / "conformance" / "escalate-ask.yaml",
        REPO_ROOT / "conformance" / "cases" / "escalate-ask.yaml",
    ),
    (
        SPACE / "conformance" / "hook-before-prose.yaml",
        REPO_ROOT / "conformance" / "cases" / "hook-before-prose.yaml",
    ),
)


@pytest.fixture(scope="module")
def playground():
    if not APP.is_file():
        pytest.skip("spaces/playground not present (sdist build)")
    spec = importlib.util.spec_from_file_location("mklang_playground_app", APP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Keep the import isolated from a previously loaded `app` module.
    sys.modules["mklang_playground_app"] = module
    spec.loader.exec_module(module)
    return module


@needs_space
@pytest.mark.parametrize("bundled, source", BUNDLED, ids=[pair[0].name for pair in BUNDLED])
def test_bundled_files_match_repo_sources(bundled: Path, source: Path) -> None:
    assert bundled.is_file(), bundled
    assert source.is_file(), source
    assert bundled.read_bytes() == source.read_bytes(), (
        f"{bundled} drifted from {source}; recopy the source file"
    )


@needs_space
def test_readme_front_matter_is_a_gradio_space() -> None:
    text = (SPACE / "README.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "sdk: gradio" in text
    assert "app_file: app.py" in text
    assert "license: apache-2.0" in text
    assert "short_description:" in text
    desc = next(
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.startswith("short_description:")
    )
    assert len(desc) <= 60
    assert "keyless" in text.lower()
    assert "path b" in text.lower()
    assert "https://github.com/gianlucamazza/mklang" in text


@needs_space
def test_requirements_install_mklang_from_this_repo() -> None:
    req = (SPACE / "requirements.txt").read_text(encoding="utf-8")
    assert "git+https://github.com/gianlucamazza/mklang.git" in req
    assert "pypi.org" not in req.lower()


@needs_space
def test_smoke_import_and_example_callback(playground) -> None:
    assert playground.demo is None or not getattr(playground.demo, "is_running", False)
    payload = json.loads(playground.run_example("hello", "accepted-first-try"))
    assert payload["ok"] is True
    assert payload["passed"] is True
    assert payload["result"]["status"] == "done"
    assert payload["mismatches"] == []


@needs_space
def test_check_and_conformance_callbacks(playground) -> None:
    source = playground.load_example_source("hello")
    checked = json.loads(playground.check_source(source))
    assert checked["ok"] is True
    parsed = json.loads(playground.parse_source(source))
    assert parsed["ok"] is True
    assert parsed["machine"] == "hello"
    case = json.loads(playground.run_conformance("escalate-ask"))
    assert case["ok"] is True
    assert case["result"]["status"] == "suspended"
    assert "checkpoint" in case
    assert case["checkpoint"]["format"] == 1
    assert case["checkpoint"]["reason"] == "escalated"
