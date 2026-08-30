#!/usr/bin/env python3
"""Validate raw experiment JSONL and build a checksum manifest for a release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from jsonschema import Draft7Validator, FormatChecker

REQUIRED_FILES = frozenset({"environments.json", "summary.json", "REPORT.md"})


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument(
        "--force", action="store_true", help="replace an existing manifest after revalidation"
    )
    args = parser.parse_args()
    if not args.release.is_dir():
        parser.error(f"release directory does not exist: {args.release}")
    missing = sorted(REQUIRED_FILES - {p.name for p in args.release.iterdir() if p.is_file()})
    jsonl_files = sorted(p for p in args.release.iterdir() if p.is_file() and p.suffix == ".jsonl")
    if missing:
        parser.error(f"release is missing required files: {', '.join(missing)}")
    if not jsonl_files:
        parser.error("release must contain at least one raw .jsonl file")
    manifest_path = args.release / "manifest.json"
    if manifest_path.exists() and not args.force:
        parser.error(f"manifest already exists: {manifest_path} (use --force to replace it)")
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "schema/experiment-result.schema.json").read_text(encoding="utf-8"))
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    files = sorted(p for p in args.release.iterdir() if p.is_file() and p.name != "manifest.json")
    errors = []
    rows = 0
    for path in jsonl_files:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path.name}:{line_no}: invalid JSON ({exc.msg})")
                continue
            row_errors = sorted(validator.iter_errors(row), key=lambda error: list(error.path))
            if row_errors:
                errors.append(f"{path.name}:{line_no}: {row_errors[0].message}")
            rows += 1
    if errors:
        for error in errors:
            print(error)
        return 1
    manifest = {
        "manifest_version": "1.0",
        "rows": rows,
        "files": {
            path.name: {"sha256": _digest(path), "bytes": path.stat().st_size} for path in files
        },
    }
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=args.release, prefix=".manifest-", delete=False
    ) as temp:
        temp.write(payload)
        temporary = Path(temp.name)
    temporary.replace(manifest_path)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
