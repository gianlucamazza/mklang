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
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets" / "demos"
TAPE_DIR = ROOT / "demos" / "tapes"
MANIFEST = ASSET_DIR / "manifest.json"
DEMOS = ("cli", "console")
FORMATS = ("webm", "gif", "txt")

SOURCE_PATTERNS = (
    "demos/tapes/*.tape",
    "scripts/demo_assets.py",
    "tests/test_demo_assets.py",
    "config/runtime.example.yaml",
    "examples/summarize_doc.mk",
    "src/mklang/cli.py",
    "src/mklang/config.py",
    "src/mklang/engine.py",
    "src/mklang/presentation.py",
    "src/mklang/providers.py",
    "src/mklang/llm/*.py",
    "src/mklang/console/*.py",
    "src/mklang/data/stdlib/std_cot.mk",
)

REQUIRED_TEXT = {
    "cli": (
        "OK examples/summarize_doc.mk",
        "findings=0",
        "DONE summarize_doc",
        "provider deepseek",
        "Result",
    ),
    "console": ("Ready", "/run std_cot", "status", "done"),
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
MAX_DURATION = 45.0
ANSI = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class DemoError(RuntimeError):
    pass


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


def source_state() -> dict:
    files = {path.relative_to(ROOT).as_posix(): _sha256(path) for path in source_files()}
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "files": files}


def _asset_path(demo: str, extension: str) -> Path:
    return ASSET_DIR / f"{demo}.{extension}"


def render() -> None:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise DemoError("DEEPSEEK_API_KEY is required for canonical live demos")
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for demo in DEMOS:
        for extension in FORMATS:
            _asset_path(demo, extension).unlink(missing_ok=True)
        _run(["vhs", str(TAPE_DIR / f"{demo}.tape")])
        _derive_gif(_asset_path(demo, "webm"), _asset_path(demo, "gif"))


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
                    f"{path.name} duration {duration:.2f}s outside {MIN_DURATION:.0f}-{MAX_DURATION:.0f}s"
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


def write_manifest(metadata: dict[str, dict] | None = None) -> None:
    from mklang import __version__

    metadata = metadata or validate()
    config = yaml.safe_load((ROOT / "config/runtime.example.yaml").read_text(encoding="utf-8"))
    tiers = config["providers"]["deepseek"]["tiers"]
    commit = _run(["git", "rev-parse", "HEAD"], capture=True)
    vhs_version = _run(["vhs", "--version"], capture=True).removeprefix("vhs version ")
    payload = {
        "schema": 1,
        "provider": "deepseek",
        "models": tiers,
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_from": commit,
        "package_version": __version__,
        "vhs_version": vhs_version,
        "source": source_state(),
        "assets": metadata,
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_drift() -> None:
    if not MANIFEST.is_file():
        raise DemoError(f"missing {MANIFEST.relative_to(ROOT)}; regenerate demos")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("provider") != "deepseek":
        raise DemoError("unsupported demo manifest or non-canonical provider")
    current = source_state()
    recorded = manifest.get("source") or {}
    if current["sha256"] != recorded.get("sha256"):
        before = recorded.get("files") or {}
        changed = sorted(
            path
            for path in set(before) | set(current["files"])
            if before.get(path) != current["files"].get(path)
        )
        raise DemoError("demo source drift: " + ", ".join(changed))
    for relative, expected in (manifest.get("assets") or {}).items():
        path = ROOT / relative
        if not path.is_file():
            raise DemoError(f"missing demo asset {relative}")
        if path.stat().st_size != expected.get("bytes") or _sha256(path) != expected.get("sha256"):
            raise DemoError(f"demo asset drift: {relative}")
    expected_assets = {f"docs/assets/demos/{demo}.{ext}" for demo in DEMOS for ext in FORMATS}
    if set((manifest.get("assets") or {})) != expected_assets:
        raise DemoError("demo manifest asset set is incomplete")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("render", "validate", "manifest", "check-drift", "all"))
    args = parser.parse_args(argv)
    try:
        if args.command in ("render", "all"):
            render()
        metadata = validate() if args.command in ("validate", "manifest", "all") else None
        if args.command in ("manifest", "all"):
            write_manifest(metadata)
        if args.command in ("check-drift", "all"):
            check_drift()
    except (DemoError, FileNotFoundError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"demo-assets: {exc}", file=sys.stderr)
        return 1
    print(f"demo-assets: {args.command} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
