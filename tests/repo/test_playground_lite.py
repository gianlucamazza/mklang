"""The static Gradio-Lite Space stays self-contained and importable offline."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys

import pytest
from conftest import REPO_ROOT

import mklang

SPACE = REPO_ROOT / "spaces" / "playground-lite"
PLAY = REPO_ROOT / "spaces" / "playground"
APP = SPACE / "app.py"
WHEEL = SPACE / f"mklang-{mklang.__version__}-py3-none-any.whl"

needs_space = pytest.mark.skipif(
    not APP.is_file(), reason="spaces/playground-lite not present (sdist build)"
)

BUNDLED = (
    "examples/hello.mkl",
    "examples/hello.test.yaml",
    "examples/triage.mkl",
    "examples/triage.test.yaml",
    "conformance/linear.yaml",
    "conformance/parse-json.yaml",
    "conformance/escalate-ask.yaml",
    "conformance/hook-before-prose.yaml",
)


@pytest.fixture(scope="module")
def playground_lite():
    if not APP.is_file():
        pytest.skip("spaces/playground-lite not present (sdist build)")
    spec = importlib.util.spec_from_file_location("mklang_playground_lite_app", APP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["mklang_playground_lite_app"] = module
    spec.loader.exec_module(module)
    return module


@needs_space
@pytest.mark.parametrize("rel", BUNDLED)
def test_lite_fixtures_match_server_playground(rel: str) -> None:
    bundled = SPACE / rel
    source = PLAY / rel
    assert bundled.is_file(), bundled
    assert source.is_file(), source
    assert bundled.read_bytes() == source.read_bytes()


@needs_space
def test_readme_is_a_static_space() -> None:
    text = (SPACE / "README.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "sdk: static" in text
    assert "sdk: gradio" not in text.split("---", 2)[1]
    assert "license: apache-2.0" in text
    desc = next(
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.startswith("short_description:")
    )
    assert len(desc) <= 60
    assert "keyless" in text.lower()
    assert "path b" in text.lower()
    assert "deps=False" in text or "deps=false" in text.lower()


@needs_space
def test_index_pins_gradio_lite_and_deps_false() -> None:
    html = (SPACE / "index.html").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/@gradio/lite@5.45.0/dist/lite.js" in html
    assert "cdn.jsdelivr.net/npm/@gradio/lite@5.45.0/dist/lite.css" in html
    assert "webworker-patched.js" in html
    assert 'src.startsWith("blob:")' in html
    assert "deps=False" in html
    assert WHEEL.name in html
    assert 'name="boot.py" entrypoint' in html
    assert f'name="{WHEEL.name}"' in html
    assert 'url="./app.py"' in html
    worker = (SPACE / "webworker-patched.js").read_text(encoding="utf-8")
    assert "huggingface-hub==0.35.0" in worker
    assert "follow_symlinks" in worker
    assert "os.link = lambda src, dst, *args, **kwargs: None" in worker
    assert "typing-extensions>=4.12.2" in worker
    assert 'isinstance(scope["query_string"], str)' in worker
    assert "openai" in html  # mentioned as not installed
    assert "extractall" in html
    assert "zipfile" in html
    assert "loadPackage" in html
    assert "jsonschema" in html


@needs_space
def test_committed_wheel_matches_package_version() -> None:
    assert WHEEL.is_file(), WHEEL
    digest = hashlib.sha256(WHEEL.read_bytes()).hexdigest()
    readme = (SPACE / "README.md").read_text(encoding="utf-8")
    assert digest in readme
    assert WHEEL.name.endswith("-py3-none-any.whl")


@needs_space
def test_lite_parse_and_check_hello(playground_lite) -> None:
    source = playground_lite.load_example_source("hello")
    parsed = json.loads(playground_lite.parse_source(source))
    assert parsed["ok"] is True
    assert parsed["machine"] == "hello"
    checked = json.loads(playground_lite.check_source(source))
    assert checked["ok"] is True
    run = json.loads(playground_lite.run_example("hello", "accepted-first-try"))
    assert run["ok"] is True
    assert run["passed"] is True


@needs_space
def test_lite_app_source_does_not_import_provider_sdks() -> None:
    text = APP.read_text(encoding="utf-8")
    assert not re.search(r"^(?:import|from)\s+(openai|textual|rich)\b", text, re.M)
    assert "judge: jev" in text or "Path B" in text
