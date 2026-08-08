"""The vendored brand assets must match the platform originals.

The docs skin borrows the platform's identity: the token palette and the "mk"
favicon are copied from mklang-platform, because the GitHub Pages build cannot
reach that repository. The platform's tokens file warns that "a copy of a
palette is a divergence with a delay" — this suite is the delay's ceiling: any
edit on either side fails the local gate of whoever holds both checkouts.

The platform repo is private, so on CI these tests skip; the comparison only
ever runs where a sibling checkout exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT.parent / "mklang-platform"

VENDORED_TOKENS = ROOT / "docs" / "assets" / "stylesheets" / "tokens.css"
PLATFORM_TOKENS = PLATFORM / "web" / "shared" / "tokens.css"

VENDORED_FAVICON = ROOT / "docs" / "assets" / "favicon.svg"
PLATFORM_FAVICON = PLATFORM / "web" / "site" / "public" / "favicon.svg"

needs_platform = pytest.mark.skipif(
    not PLATFORM.is_dir(),
    reason="sibling mklang-platform checkout not present (private repo; local gate only)",
)


def _tokens_body(text: str) -> str:
    """Everything from the :root block on — the headers legitimately differ.

    Anchored to the line start: the platform header mentions ":root" in prose.
    """
    marker = "\n:root {"
    assert marker in text, "tokens file lost its :root block"
    return text[text.index(marker) :]


def test_vendored_files_exist() -> None:
    """The skin must not silently lose its assets, platform checkout or not."""
    assert VENDORED_TOKENS.is_file()
    assert VENDORED_FAVICON.is_file()


def test_vendored_tokens_declare_their_origin() -> None:
    header = VENDORED_TOKENS.read_text(encoding="utf-8").split(":root")[0]
    assert "mklang-platform/web/shared/tokens.css" in header


@needs_platform
def test_tokens_match_platform() -> None:
    vendored = _tokens_body(VENDORED_TOKENS.read_text(encoding="utf-8"))
    upstream = _tokens_body(PLATFORM_TOKENS.read_text(encoding="utf-8"))
    assert vendored == upstream, (
        "token drift: re-vendor with\n"
        f"  sed -n '/^:root {{/,$p' {PLATFORM_TOKENS} >> (fresh header in) {VENDORED_TOKENS}"
    )


@needs_platform
def test_favicon_matches_platform() -> None:
    assert VENDORED_FAVICON.read_bytes() == PLATFORM_FAVICON.read_bytes(), (
        f"favicon drift: cp {PLATFORM_FAVICON} {VENDORED_FAVICON}"
    )
