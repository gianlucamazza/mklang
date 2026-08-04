#!/usr/bin/env python3
"""Render and validate the live CLI/console demos committed with the docs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets" / "demos"
TAPE_DIR = ROOT / "demos" / "tapes"
TOOLCHAIN_FILE = ROOT / "demos" / "toolchain.conf"
MANIFEST = ASSET_DIR / "manifest.json"
DEMOS = ("agent", "language")
FORMATS = ("webm", "gif", "txt")

PROVIDER = "deepseek"

# Only the files the two live demos actually exercise. (agent → console +
# news_search live web; language → react.mkl + the calc tool via the CLI.)
#
# Editing one of these makes the recordings *suspect*, not stale: it is a signal that a
# regeneration may be due, and `check-drift` says so without failing. What it cannot do
# is decide — 35 of the 42 manifest commits in the 90 days to 2026-08-04 re-pinned these
# hashes with the assets byte-identical, because the changed file did not alter anything
# on screen. A gate that is right one time in six is answering the wrong question; the
# freshness guarantee lives in `MAX_AGE_DAYS` and the scheduled regeneration instead.
#
# Two entries are deliberately absent. `src/mklang/cli.py` is the most-edited file in the
# repository (41 commits in that same window) and the demos show a handful of its output
# lines: no file-level hash can tell those apart. `config/runtime.example.yaml` is here
# instead as a *section* — see `_provider_section_digest` — because the demos run against
# one provider and the rest of that file is never on screen.
SOURCE_PATTERNS = (
    "demos/tapes/*.tape",
    "demos/toolchain.conf",
    "scripts/demo_assets.py",
    "examples/react.mkl",
    "examples/news_search.mkl",
    "src/mklang/search.py",
    "src/mklang/tools.py",
    "src/mklang/data/console/agent.mkl",
    "src/mklang/config.py",
    "src/mklang/engine.py",
    "src/mklang/presentation.py",
    "src/mklang/providers.py",
    "src/mklang/llm/*.py",
    "src/mklang/console/*.py",
)

RUNTIME_EXAMPLE = ROOT / "config" / "runtime.example.yaml"
# Written like a path with a fragment so a drift message names what actually moved.
PROVIDER_SECTION_KEY = f"config/runtime.example.yaml#providers.{PROVIDER}"

REQUIRED_TEXT = {
    "agent": (
        "Ready",
        "default cost budget",
        "console_agent",
        "do_run",
        "boil that down",
    ),
    "language": (
        "OK",
        "react.mkl",
        "findings=0",
        "DONE react",
        "provider deepseek",
        "Result",
        "153",
        "steps",
    ),
}
FORBIDDEN_TEXT = (
    "Traceback (most recent call last)",
    "provider-error",
    "API_KEY=",
    "Authorization: Bearer",
)

WEBM_MAX = 3 * 1024 * 1024
GIF_MAX = 5 * 1024 * 1024
TOTAL_MAX = 16 * 1024 * 1024
MIN_DURATION = 8.0
# Agent + live web is latency-variable; 2026-07-27 CI hit ~63s wall playback.
MAX_DURATION = 75.0
# The freshness guarantee that replaces "the sources have not moved". Weaker and true,
# rather than strong and asserted by hand: past this, the recordings are describing a
# version of the software nobody is running. Checked from `generated_at`, reported by
# `staleness`, and acted on by the scheduled regeneration — never by failing a build.
MAX_AGE_DAYS = 90
# A tape that fails twice is a real failure; a tape that fails once is usually the
# provider being slow. Two attempts, not more: past that the run is paying for latency.
RENDER_ATTEMPTS = 2
RETRY_PAUSE_SECONDS = 5
ANSI = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class DemoError(RuntimeError):
    pass


def toolchain_config() -> dict[str, str]:
    values = {
        key: value for key, value in dotenv_values(TOOLCHAIN_FILE).items() if value is not None
    }
    required = {
        "VHS_VERSION",
        "VHS_ARCHIVE_SHA256",
        "FONT_FAMILY",
        "FONT_VERSION",
        "FONT_ARCHIVE_SHA256",
    }
    missing = sorted(required - values.keys())
    if missing:
        raise DemoError("missing demo toolchain values: " + ", ".join(missing))
    return values


def _run(args: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
        env={**os.environ, "TERM": "xterm-256color"},
    )
    return result.stdout.strip() if capture else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files() -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_PATTERNS:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    if not paths:
        raise DemoError("no demo source files matched")
    return sorted(paths)


def _provider_section_digest() -> str:
    """Hash of the canonical provider's block in the runtime example, not of the file.

    The demos run against `PROVIDER` and never show the other providers, so renaming a
    model in the OpenAI block used to invalidate two recordings it does not appear in.
    Hashing the parsed section also makes the digest immune to comment and whitespace
    edits, which is the majority of what that file receives.
    """
    config = yaml.safe_load(RUNTIME_EXAMPLE.read_text(encoding="utf-8"))
    try:
        section = config["providers"][PROVIDER]
    except (KeyError, TypeError) as exc:
        raise DemoError(
            f"{RUNTIME_EXAMPLE.relative_to(ROOT)} has no providers.{PROVIDER} block"
        ) from exc
    encoded = json.dumps(section, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def source_state() -> dict:
    files = {path.relative_to(ROOT).as_posix(): _sha256(path) for path in source_files()}
    files[PROVIDER_SECTION_KEY] = _provider_section_digest()
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "files": files}


def _asset_path(demo: str, extension: str) -> Path:
    return ASSET_DIR / f"{demo}.{extension}"


def render() -> None:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise DemoError("DEEPSEEK_API_KEY is required for canonical live demos")
    _verify_render_toolchain()
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for demo in DEMOS:
        _render_one(demo)
        _normalize_transcript(_asset_path(demo, "txt"))
        _derive_gif(_asset_path(demo, "webm"), _asset_path(demo, "gif"))


def _render_one(demo: str, attempts: int = RENDER_ATTEMPTS) -> None:
    """One tape, retried once.

    The tapes wait on strings appearing on screen, from a console talking to a live
    provider and a live search API. When the answer is slower than the tape's window,
    VHS times out and the job dies — 2 successes in 7 runs to 2026-08-04, and the
    failures were latency, not the change under test.

    Retried per demo rather than per job: `DEMOS` renders in order, so without this a
    slow `agent` also throws away a `language` that would have succeeded.
    """
    last: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        for extension in FORMATS:
            _asset_path(demo, extension).unlink(missing_ok=True)
        try:
            _run(["vhs", str(TAPE_DIR / f"{demo}.tape")])
            return
        except subprocess.CalledProcessError as exc:
            last = exc
            if attempt < attempts:
                print(
                    f"demo-assets: {demo} tape failed (attempt {attempt}/{attempts}); "
                    "retrying — live latency is the usual cause",
                    file=sys.stderr,
                )
                time.sleep(RETRY_PAUSE_SECONDS)
    assert last is not None
    raise last


def _verify_render_toolchain() -> None:
    config = toolchain_config()
    vhs_version = _run(["vhs", "--version"], capture=True)
    if f"v{config['VHS_VERSION']}" not in vhs_version:
        raise DemoError(
            f"VHS version mismatch: expected {config['VHS_VERSION']}, got {vhs_version}"
        )
    resolved_font = _run(["fc-match", "--format=%{family}", config["FONT_FAMILY"]], capture=True)
    if resolved_font != config["FONT_FAMILY"]:
        raise DemoError(f"font mismatch: expected {config['FONT_FAMILY']!r}, got {resolved_font!r}")


def _derive_gif(source: Path, target: Path) -> None:
    filter_graph = (
        "[0:v]fps=12,scale=960:540:flags=lanczos,split[s0][s1];"
        "[s0]palettegen=max_colors=96:stats_mode=diff[p];"
        "[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-filter_complex",
            filter_graph,
            "-loop",
            "0",
            str(target),
        ]
    )


def _probe(path: Path) -> dict:
    raw = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(raw)


def _clean_transcript(path: Path) -> str:
    return ANSI.sub("", path.read_text(encoding="utf-8", errors="replace"))


# Pure box / rule chrome captured by VHS snapshots (no semantic content).
_CHROME = re.compile(r"^[\s─━═╭╮╯╰│┌┐└┘├┤┬┴┼╔╗╚╝║▔▁▂]+$")


def _is_typing_prefix(earlier: str, later: str) -> bool:
    """True when *earlier* is an intermediate VHS frame of typing *later*."""
    a, b = earlier.rstrip(), later.rstrip()
    if not a or a == b or len(a) >= len(b):
        return False
    if not b.startswith(a):
        return False
    # Only collapse progressive command/prompt typing, not prose replies.
    sample = a.lstrip()
    return sample.startswith((">", "PYTHONPATH", "python ", "/")) or "python -m mklang" in sample


def _normalize_transcript_lines(raw_lines: list[str]) -> list[str]:
    """Collapse VHS multi-frame noise into a compact, readable transcript."""
    lines: list[str] = []
    seen: set[str] = set()
    for raw in raw_lines:
        line = ANSI.sub("", raw).rstrip()
        stripped = line.strip()
        if not stripped or stripped == ">":
            continue
        if _CHROME.fullmatch(stripped):
            continue
        if line not in seen:
            seen.add(line)
            lines.append(line)

    # Drop intermediate typing frames (a strict prefix of a nearby later line).
    kept: list[str] = []
    for i, line in enumerate(lines):
        window = lines[i + 1 : i + 16]
        if any(_is_typing_prefix(line, other) for other in window):
            continue
        kept.append(line)
    return kept


def _normalize_transcript(path: Path) -> None:
    """Turn VHS screen snapshots into a compact, readable plain-text transcript."""
    text = path.read_text(encoding="utf-8", errors="replace")
    cleaned = _normalize_transcript_lines(text.splitlines())
    path.write_text("\n".join(cleaned) + "\n", encoding="utf-8")


def validate() -> dict[str, dict]:
    errors: list[str] = []
    metadata: dict[str, dict] = {}
    total = 0
    secret = os.environ.get("DEEPSEEK_API_KEY")

    for demo in DEMOS:
        transcript_path = _asset_path(demo, "txt")
        if not transcript_path.is_file():
            errors.append(f"missing {transcript_path.relative_to(ROOT)}")
            continue
        transcript = _clean_transcript(transcript_path)
        folded = transcript.casefold()
        for marker in REQUIRED_TEXT[demo]:
            if marker.casefold() not in folded:
                errors.append(f"{demo}.txt is missing marker {marker!r}")
        for marker in FORBIDDEN_TEXT:
            if marker.casefold() in folded:
                errors.append(f"{demo}.txt contains forbidden marker {marker!r}")
        if secret and secret in transcript:
            errors.append(f"{demo}.txt contains DEEPSEEK_API_KEY")

        for extension in ("webm", "gif"):
            path = _asset_path(demo, extension)
            if not path.is_file():
                errors.append(f"missing {path.relative_to(ROOT)}")
                continue
            size = path.stat().st_size
            total += size
            limit = WEBM_MAX if extension == "webm" else GIF_MAX
            if size > limit:
                errors.append(f"{path.name} is {size} bytes (limit {limit})")
            probe = _probe(path)
            videos = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
            audios = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
            if len(videos) != 1:
                errors.append(f"{path.name} must contain exactly one video stream")
                continue
            video = videos[0]
            expected = (1200, 675) if extension == "webm" else (960, 540)
            actual = (video.get("width"), video.get("height"))
            if actual != expected:
                errors.append(f"{path.name} dimensions {actual}, expected {expected}")
            if audios:
                errors.append(f"{path.name} must not contain audio")
            duration = float(probe.get("format", {}).get("duration") or 0)
            if not MIN_DURATION <= duration <= MAX_DURATION:
                errors.append(
                    f"{path.name} duration {duration:.2f}s outside "
                    f"{MIN_DURATION:.0f}-{MAX_DURATION:.0f}s"
                )
            metadata[path.relative_to(ROOT).as_posix()] = {
                "bytes": size,
                "sha256": _sha256(path),
                "width": actual[0],
                "height": actual[1],
                "duration_seconds": round(duration, 3),
                "codec": video.get("codec_name"),
            }

        metadata[transcript_path.relative_to(ROOT).as_posix()] = {
            "bytes": transcript_path.stat().st_size,
            "sha256": _sha256(transcript_path),
        }

    if total > TOTAL_MAX:
        errors.append(f"binary demo assets total {total} bytes (limit {TOTAL_MAX})")
    if errors:
        raise DemoError("demo validation failed:\n- " + "\n- ".join(errors))
    return metadata


def _provenance(metadata: dict[str, dict], commit: str) -> tuple[str, str]:
    """When these recordings were made — not when the manifest was last rewritten.

    `manifest` is run on its own to re-pin source hashes, with the assets untouched.
    Stamping a fresh `generated_at` there would reset the clock `MAX_AGE_DAYS` reads,
    so a file that never changes could keep the recordings "fresh" forever while they
    aged. The timestamp therefore moves only when an asset hash does.
    """
    if MANIFEST.is_file():
        previous = json.loads(MANIFEST.read_text(encoding="utf-8"))
        unchanged = {
            path: entry.get("sha256") for path, entry in (previous.get("assets") or {}).items()
        } == {path: entry.get("sha256") for path, entry in metadata.items()}
        if unchanged and previous.get("generated_at") and previous.get("generated_from"):
            return str(previous["generated_at"]), str(previous["generated_from"])
    return datetime.now(UTC).isoformat(), commit


def write_manifest(metadata: dict[str, dict] | None = None) -> None:
    from mklang import __version__

    metadata = metadata or validate()
    config = yaml.safe_load(RUNTIME_EXAMPLE.read_text(encoding="utf-8"))
    tiers = config["providers"][PROVIDER]["tiers"]
    commit = _run(["git", "rev-parse", "HEAD"], capture=True)
    vhs_version = _run(["vhs", "--version"], capture=True).removeprefix("vhs version ")
    toolchain = toolchain_config()
    generated_at, generated_from = _provenance(metadata, commit)
    payload = {
        "schema": 2,
        "provider": PROVIDER,
        "models": tiers,
        "generated_at": generated_at,
        "generated_from": generated_from,
        "package_version": __version__,
        "toolchain": {
            "vhs": {
                "version": toolchain["VHS_VERSION"],
                "archive_sha256": toolchain["VHS_ARCHIVE_SHA256"],
                "reported_version": vhs_version,
            },
            "font": {
                "family": toolchain["FONT_FAMILY"],
                "version": toolchain["FONT_VERSION"],
                "archive_sha256": toolchain["FONT_ARCHIVE_SHA256"],
            },
        },
        "source": source_state(),
        "assets": metadata,
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_manifest() -> dict:
    if not MANIFEST.is_file():
        raise DemoError(f"missing {MANIFEST.relative_to(ROOT)}; regenerate demos")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema") != 2 or manifest.get("provider") != PROVIDER:
        raise DemoError("unsupported demo manifest or non-canonical provider")
    return manifest


def staleness(manifest: dict | None = None) -> dict:
    """Whether the recordings are worth regenerating — a report, never a verdict.

    Two independent reasons, deliberately kept apart from `check_drift`: a source moved
    (the recordings *might* be out of date, and only a person or a re-render can say),
    or they are older than `MAX_AGE_DAYS` (they describe a version nobody runs).

    Neither is an error. This is what the scheduled regeneration reads to decide whether
    to spend live provider calls, and what `check-drift` prints so the person who touched
    a source knows why nothing failed.
    """
    manifest = manifest if manifest is not None else _read_manifest()
    current = source_state()
    recorded = manifest.get("source") or {}
    changed: list[str] = []
    if current["sha256"] != recorded.get("sha256"):
        before = recorded.get("files") or {}
        changed = sorted(
            path
            for path in set(before) | set(current["files"])
            if before.get(path) != current["files"].get(path)
        )

    age_days: float | None = None
    generated_at = manifest.get("generated_at")
    if generated_at:
        try:
            age_days = (datetime.now(UTC) - datetime.fromisoformat(generated_at)).days
        except ValueError:
            age_days = None

    expired = age_days is not None and age_days > MAX_AGE_DAYS
    return {
        "changed_sources": changed,
        "age_days": age_days,
        "expired": expired,
        "stale": bool(changed) or expired,
    }


def report_staleness(manifest: dict | None = None) -> dict:
    """`staleness`, said out loud on stderr. Returns the report so callers can branch."""
    report = staleness(manifest)
    if report["changed_sources"]:
        print(
            "demo-assets: sources moved since these recordings were made: "
            + ", ".join(report["changed_sources"])
            + "\n  This is a notice, not a failure. If the change alters what the demos"
            " show, regenerate them (Demo assets workflow); if it does not, re-pin with"
            " `demo_assets.py manifest` or leave it to the scheduled run.",
            file=sys.stderr,
        )
    if report["expired"]:
        print(
            f"demo-assets: recordings are {report['age_days']} days old "
            f"(limit {MAX_AGE_DAYS}); the scheduled regeneration will refresh them.",
            file=sys.stderr,
        )
    return report


def check_drift() -> None:
    """The half that blocks: nobody has edited the published assets by hand.

    Source drift used to fail here too, and that is what this function stopped doing —
    see the note above `SOURCE_PATTERNS`. It is reported by `report_staleness` instead.
    """
    manifest = _read_manifest()
    toolchain = toolchain_config()
    expected_toolchain = {
        "vhs": {
            "version": toolchain["VHS_VERSION"],
            "archive_sha256": toolchain["VHS_ARCHIVE_SHA256"],
        },
        "font": {
            "family": toolchain["FONT_FAMILY"],
            "version": toolchain["FONT_VERSION"],
            "archive_sha256": toolchain["FONT_ARCHIVE_SHA256"],
        },
    }
    recorded_toolchain = manifest.get("toolchain") or {}
    for component, expected in expected_toolchain.items():
        recorded = recorded_toolchain.get(component) or {}
        if any(recorded.get(key) != value for key, value in expected.items()):
            raise DemoError(f"demo toolchain drift: {component}")
    for relative, expected in (manifest.get("assets") or {}).items():
        path = ROOT / relative
        if not path.is_file():
            raise DemoError(f"missing demo asset {relative}")
        if path.stat().st_size != expected.get("bytes") or _sha256(path) != expected.get("sha256"):
            raise DemoError(f"demo asset drift: {relative}")
    expected_assets = {f"docs/assets/demos/{demo}.{ext}" for demo in DEMOS for ext in FORMATS}
    if set(manifest.get("assets") or {}) != expected_assets:
        raise DemoError("demo manifest asset set is incomplete")
    # Also guard the on-disk set: a demo removed from DEMOS leaves orphan asset
    # files (its tape is gone, but the rendered webm/gif/txt linger). The
    # manifest check above cannot see them; this does.
    on_disk = {f"docs/assets/demos/{p.name}" for ext in FORMATS for p in ASSET_DIR.glob(f"*.{ext}")}
    orphans = sorted(on_disk - expected_assets)
    if orphans:
        raise DemoError("orphan demo assets (not in DEMOS): " + ", ".join(orphans))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("render", "validate", "manifest", "check-drift", "staleness", "all"),
    )
    args = parser.parse_args(argv)
    try:
        if args.command in ("render", "all"):
            render()
        metadata = validate() if args.command in ("validate", "manifest", "all") else None
        if args.command in ("manifest", "all"):
            write_manifest(metadata)
        if args.command in ("check-drift", "all"):
            check_drift()
            report_staleness()
        if args.command == "staleness":
            # The one command that exits non-zero without anything being wrong: it is a
            # question ("is a regeneration due?"), asked by the scheduled workflow so it
            # can skip the live provider calls when the answer is no.
            report = report_staleness()
            print(f"demo-assets: staleness stale={report['stale']}")
            return 1 if report["stale"] else 0
    except (DemoError, FileNotFoundError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"demo-assets: {exc}", file=sys.stderr)
        return 1
    print(f"demo-assets: {args.command} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
