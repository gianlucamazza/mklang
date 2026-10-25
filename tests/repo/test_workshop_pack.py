"""Honesty locks for the unpublished workshop case-study pack (issue #121)."""

from __future__ import annotations

import pytest
from conftest import REPO_ROOT

PACK = REPO_ROOT / "docs" / "workshop" / "case-study-pack.md"
INDEX = REPO_ROOT / "docs" / "workshop" / "README.md"

needs_pack = pytest.mark.skipif(
    not PACK.is_file(), reason="docs/workshop not present (sdist build)"
)

# Words that would turn this pack into the #122 venue/abstract track.
_VENUE_LEAKS = (
    "neurips",
    "camera-ready",
    "camera ready",
    "submit to",
    "submission",
    "call for papers",
    "deadline",
    "impact factor",
)

_PATH_B_RECEIPT = "https://github.com/gianlucamazza/mklang/issues/123#issuecomment-5999319763"
_MERGE_READY_COMMENT = "issuecomment-5999361559"


@needs_pack
def test_pack_is_historical_and_unpublished() -> None:
    text = PACK.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    nav = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assemble = (REPO_ROOT / "scripts" / "build-docs.sh").read_text(encoding="utf-8")
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "historical" in text.lower()
    assert "pending M4 (paid run, not yet approved)" in text
    assert "pending M4 (paid run, not yet approved)" in index
    assert "not run" in text.lower()
    assert "#60" in text
    assert "production_ready: false" in text
    assert "small-n" in text.lower() or "small **n**" in text.lower()
    assert "priority_shadow" in text
    assert "none_holds" in text

    lower = text.lower()
    for leak in _VENUE_LEAKS:
        assert leak not in lower, f"venue/submission language leaked: {leak}"

    assert "case-study-pack.md" not in nav
    assert not any(
        line.lstrip().startswith("- ") and "workshop/" in line and ".md" in line
        for line in nav.splitlines()
    )
    assert "docs/workshop/" in assemble
    assert "stay off the site" in assemble
    # Unpublished: no site-facing pointer until Docs' honesty pass.
    assert "docs/workshop/" not in roadmap
    unreleased = changelog.split("## [1.4.0]", 1)[0]
    assert "docs/workshop/" not in unreleased
    assert "case-study-pack.md" not in unreleased


@needs_pack
def test_pack_cites_path_b_receipt_and_avoids_secrets() -> None:
    text = PACK.read_text(encoding="utf-8")
    path_b_lines = [
        line
        for line in text.splitlines()
        if "Path B first-true" in line or "Path B `priority_shadow`" in line
    ]
    assert path_b_lines, "missing Path B first-true / source-register lines"
    joined = "\n".join(path_b_lines)
    assert "#issuecomment-5999319763" in joined
    assert _PATH_B_RECEIPT in text
    assert "n=6 machines" in joined
    assert "one pinned entry-state item" in joined
    assert "8773760f" in joined
    assert "00e88c73" in joined
    assert _MERGE_READY_COMMENT not in text

    assert "docs/experiments/gate-divergence.md" in text
    assert "3983472" in text
    assert "README.md" in text
    assert "what-mklang-is.md" in text

    lowered = text.lower()
    assert "sk-ant-" not in lowered
    assert "api_key=" not in lowered
    assert "/workspace/lab-briefs" not in lowered
    assert "github_run_id" not in lowered
