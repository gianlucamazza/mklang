"""Unit tests for demo asset helpers (no live render)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "demo_assets.py"

# Invented, not read from the repository. This suite also runs against an extracted
# sdist (the AUR check surface), where `demos/toolchain.conf` and the tapes are not
# shipped — reading either there turns a unit test into a packaging assertion.
TOOLCHAIN = {
    "VHS_VERSION": "9.9.9",
    "VHS_ARCHIVE_SHA256": "a" * 64,
    "FONT_FAMILY": "Test Mono",
    "FONT_VERSION": "1.0",
    "FONT_ARCHIVE_SHA256": "b" * 64,
}
SOURCE = {"sha256": "pinned", "files": {"src/mklang/tools.py": "c" * 64}}


@pytest.fixture(scope="module")
def demo_assets():
    spec = importlib.util.spec_from_file_location("demo_assets", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_assets(demo_assets, tmp_path, monkeypatch):
    """A minimal asset directory plus a manifest that agrees with it.

    Enough for `check_drift` and `staleness` without rendering anything: the files hold
    placeholder bytes, and the manifest records their real hashes.
    """
    asset_dir = tmp_path / "docs" / "assets" / "demos"
    asset_dir.mkdir(parents=True)
    assets = {}
    for demo in demo_assets.DEMOS:
        for extension in demo_assets.FORMATS:
            path = asset_dir / f"{demo}.{extension}"
            path.write_bytes(f"{demo}.{extension}".encode())
            assets[f"docs/assets/demos/{demo}.{extension}"] = {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }

    manifest_path = asset_dir / "manifest.json"

    def write(source: dict | None = None, generated_at: str | None = None) -> None:
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": 2,
                    "provider": demo_assets.PROVIDER,
                    "generated_at": generated_at or datetime.now(UTC).isoformat(),
                    "generated_from": "0" * 40,
                    "toolchain": {
                        "vhs": {
                            "version": TOOLCHAIN["VHS_VERSION"],
                            "archive_sha256": TOOLCHAIN["VHS_ARCHIVE_SHA256"],
                        },
                        "font": {
                            "family": TOOLCHAIN["FONT_FAMILY"],
                            "version": TOOLCHAIN["FONT_VERSION"],
                            "archive_sha256": TOOLCHAIN["FONT_ARCHIVE_SHA256"],
                        },
                    },
                    "source": source if source is not None else SOURCE,
                    "assets": assets,
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(demo_assets, "ROOT", tmp_path)
    monkeypatch.setattr(demo_assets, "ASSET_DIR", asset_dir)
    monkeypatch.setattr(demo_assets, "MANIFEST", manifest_path)
    monkeypatch.setattr(demo_assets, "source_state", lambda: SOURCE)
    monkeypatch.setattr(demo_assets, "toolchain_config", lambda: TOOLCHAIN)
    write()
    return type("FakeAssets", (), {"dir": asset_dir, "manifest": manifest_path, "write": write})


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


# --------------------------------------------------------------------------- #
# What still blocks: the published recordings themselves.
# --------------------------------------------------------------------------- #


def test_edited_asset_fails(demo_assets, fake_assets) -> None:
    (fake_assets.dir / "agent.txt").write_bytes(b"tampered")
    with pytest.raises(demo_assets.DemoError, match="asset drift"):
        demo_assets.check_drift()


def test_missing_asset_fails(demo_assets, fake_assets) -> None:
    (fake_assets.dir / "language.webm").unlink()
    with pytest.raises(demo_assets.DemoError, match="missing demo asset"):
        demo_assets.check_drift()


def test_orphan_asset_fails(demo_assets, fake_assets) -> None:
    """A demo dropped from DEMOS leaves rendered files behind; the manifest cannot see them."""
    (fake_assets.dir / "retired.webm").write_bytes(b"left over")
    with pytest.raises(demo_assets.DemoError, match="orphan demo assets"):
        demo_assets.check_drift()


def test_toolchain_drift_fails(demo_assets, fake_assets) -> None:
    manifest = json.loads(fake_assets.manifest.read_text())
    manifest["toolchain"]["vhs"]["version"] = "0.0.1"
    fake_assets.manifest.write_text(json.dumps(manifest))
    with pytest.raises(demo_assets.DemoError, match="toolchain drift"):
        demo_assets.check_drift()


# --------------------------------------------------------------------------- #
# What stopped blocking, and is the regression this change introduces on purpose.
# --------------------------------------------------------------------------- #


def test_source_drift_is_a_notice_not_a_failure(demo_assets, fake_assets) -> None:
    stale_source = {"sha256": "stale", "files": {"src/mklang/tools.py": "old"}}
    fake_assets.write(source=stale_source)

    demo_assets.check_drift()  # must not raise: that is the whole point

    report = demo_assets.staleness()
    assert "src/mklang/tools.py" in report["changed_sources"]
    assert report["stale"] is True
    assert report["expired"] is False


def test_age_past_the_limit_is_stale_without_being_an_error(demo_assets, fake_assets) -> None:
    old = datetime.now(UTC) - timedelta(days=demo_assets.MAX_AGE_DAYS + 1)
    fake_assets.write(generated_at=old.isoformat())

    demo_assets.check_drift()

    report = demo_assets.staleness()
    assert report["expired"] is True
    assert report["stale"] is True
    assert report["changed_sources"] == []


def test_fresh_and_unmoved_is_not_stale(demo_assets, fake_assets) -> None:
    report = demo_assets.staleness()
    assert report == {"changed_sources": [], "age_days": 0, "expired": False, "stale": False}


# --------------------------------------------------------------------------- #
# The clock the age check reads must not be resettable by re-pinning.
# --------------------------------------------------------------------------- #


def test_repinning_keeps_the_original_generation_time(demo_assets, fake_assets) -> None:
    manifest = json.loads(fake_assets.manifest.read_text())
    generated_at, generated_from = demo_assets._provenance(manifest["assets"], "newcommit")
    assert generated_at == manifest["generated_at"]
    assert generated_from == manifest["generated_from"]


def test_a_changed_asset_does_move_the_clock(demo_assets, fake_assets) -> None:
    manifest = json.loads(fake_assets.manifest.read_text())
    rendered = {path: dict(entry) for path, entry in manifest["assets"].items()}
    rendered["docs/assets/demos/agent.webm"]["sha256"] = "different"
    generated_at, generated_from = demo_assets._provenance(rendered, "newcommit")
    assert generated_at != manifest["generated_at"]
    assert generated_from == "newcommit"


# --------------------------------------------------------------------------- #
# The provider section fingerprint, and the render retry.
# --------------------------------------------------------------------------- #


def test_provider_section_digest_ignores_the_rest_of_the_file(demo_assets, tmp_path, monkeypatch):
    """Renaming a model under another provider must not invalidate the recordings."""
    before = tmp_path / "before.yaml"
    before.write_text(
        "providers:\n"
        f"  {demo_assets.PROVIDER}:\n"
        "    tiers:\n"
        "      fast: x-flash\n"
        "  openai:\n"
        "    tiers:\n"
        "      fast: gpt-a\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(demo_assets, "RUNTIME_EXAMPLE", before)
    original = demo_assets._provider_section_digest()

    after = tmp_path / "after.yaml"
    after.write_text(
        "# a comment the demos never show\n"
        "providers:\n"
        f"  {demo_assets.PROVIDER}:\n"
        "    tiers:\n"
        "      fast: x-flash\n"
        "  openai:\n"
        "    tiers:\n"
        "      fast: gpt-b\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(demo_assets, "RUNTIME_EXAMPLE", after)
    assert demo_assets._provider_section_digest() == original

    changed = tmp_path / "changed.yaml"
    changed.write_text(
        f"providers:\n  {demo_assets.PROVIDER}:\n    tiers:\n      fast: x-pro\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(demo_assets, "RUNTIME_EXAMPLE", changed)
    assert demo_assets._provider_section_digest() != original


def test_render_retries_a_flaky_tape_once(demo_assets, fake_assets, monkeypatch) -> None:
    calls: list[list[str]] = []

    def flaky(args, *, capture=False):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, args)
        return ""

    monkeypatch.setattr(demo_assets, "_run", flaky)
    monkeypatch.setattr(demo_assets.time, "sleep", lambda _: None)
    demo_assets._render_one("agent")
    assert len(calls) == 2


def test_render_gives_up_after_the_retry(demo_assets, fake_assets, monkeypatch) -> None:
    calls: list[list[str]] = []

    def always_fails(args, *, capture=False):
        calls.append(args)
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(demo_assets, "_run", always_fails)
    monkeypatch.setattr(demo_assets.time, "sleep", lambda _: None)
    with pytest.raises(subprocess.CalledProcessError):
        demo_assets._render_one("agent")
    assert len(calls) == demo_assets.RENDER_ATTEMPTS
