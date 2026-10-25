"""Score the five-reader register deterministically without running sessions or filling it.

Usage: uv run python scripts/five_reader_register.py --check [--path protocol.md]
Prints a JSON report; --check fails when rows or the recorded headline disagree.
Uses only the standard library and makes no network or model calls.

Exit codes:
  0 = register read (and, with --check, no errors)
  1 = --check found errors (rows or headline disagree)
  2 = register can't be read/parsed (missing file, missing section/table,
      malformed rows); argparse also exits 2 for bad or unknown flags
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "docs/experiments/distribution-five-reader.md"
BRANCH_POSITIONING = "positioning problem"
BRANCH_PITCH = "best use absent from the pitch"
BRANCH_WORKING = "distribution working"
PLACEHOLDER = "n/5 understood · n/5 tried · branch: —"
HEADLINE_PREFIX = "**Headline (fill after run):**"


@dataclass(frozen=True)
class Row:
    number: str
    venue: str
    question: str
    understood: str
    tried: str

    @property
    def pending(self) -> bool:
        return not any((self.venue, self.question, self.understood, self.tried))


@dataclass(frozen=True)
class Counts:
    understood: int
    not_understood: int
    tried: int
    tried_unchecked: int


@dataclass(frozen=True)
class Report:
    status: str
    rows: list[Row]
    counts: Counts | None
    branch: str | None
    expected_headline: str
    actual_headline: str | None
    errors: list[str]


def score(rows: Sequence[Row], actual_headline: str | None = None) -> Report:
    """Validate normalized rows and score only a complete, valid register.

    Invalid registers have status 'invalid' and no counts or branch.
    """
    errors: list[str] = []
    if len(rows) != 5 or [row.number for row in rows] != list("12345"):
        errors.append("register must have exactly 5 rows numbered 1..5")
    for row in rows:
        if row.pending:
            continue
        for field in ("venue", "question"):
            if not getattr(row, field):
                errors.append(f"row {row.number}: {field} must be non-empty")
        if row.understood.lower() not in {"yes", "no"}:
            errors.append(f"row {row.number}: understood must be yes or no")
        if row.tried.lower() not in {"yes", "no", ""}:
            errors.append(f"row {row.number}: tried must be yes, no or empty")

    pending = sum(row.pending for row in rows)
    status = (
        "invalid" if errors else "pending" if pending == 5 else "partial" if pending else "complete"
    )
    counts = None
    branch = None
    expected = PLACEHOLDER
    if status == "complete":
        counts = Counts(
            understood=sum(row.understood.lower() == "yes" for row in rows),
            not_understood=sum(row.understood.lower() == "no" for row in rows),
            tried=sum(row.tried.lower() == "yes" for row in rows),
            tried_unchecked=sum(row.tried == "" for row in rows),
        )
        if counts.not_understood >= 3:
            branch = BRANCH_POSITIONING
        elif counts.understood >= 3:
            if counts.tried >= 1:
                branch = BRANCH_WORKING
            elif counts.tried_unchecked == 0:
                branch = BRANCH_PITCH
        expected = (
            f"{counts.understood}/5 understood · {counts.tried}/5 tried · branch: {branch or '—'}"
        )
    if not errors and actual_headline != expected:
        errors.append(f"headline disagrees; paste this line: {HEADLINE_PREFIX} _{expected}_")
    return Report(status, list(rows), counts, branch, expected, actual_headline, errors)


def parse_register(text: str) -> Report:
    """Parse the results section; raise ValueError when its table is unreadable."""
    section = re.search(r"^## Results register\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if section is None:
        raise ValueError("missing Results register section")
    lines = section.group(1).splitlines()
    header = next((i for i, line in enumerate(lines) if line.startswith("| # |")), None)
    if header is None:
        raise ValueError("missing results register table")
    rows: list[Row] = []
    for line in lines[header + 1 :]:
        if not line.strip().startswith("|"):
            break
        table_line = line.strip()
        if not table_line.endswith("|"):
            raise ValueError("results register table rows must end with |")
        # Only \| escapes a pipe in a cell; a literal backslash immediately
        # before a pipe cannot be written.
        cells = [
            cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", table_line[1:-1])
        ]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if len(cells) != 5:
            raise ValueError("results register table rows must have 5 columns")
        cells = ["" if cell == "_pending_" else cell for cell in cells]
        rows.append(Row(*cells))
    actual = None
    for line in lines:
        if line.startswith(HEADLINE_PREFIX):
            match = re.fullmatch(r"_(.*)_", line[len(HEADLINE_PREFIX) :].strip())
            actual = match.group(1) if match else None
            break
    return score(rows, actual)


def _ensure_utf8_streams() -> None:
    """Write UTF-8 even when stdout/stderr default to a legacy code page (e.g. cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        # Replaced streams (StringIO, test capture) are not TextIOWrapper; leave them alone.
        if not isinstance(stream, io.TextIOWrapper):
            continue
        if (stream.encoding or "").lower().replace("-", "") != "utf8":
            with contextlib.suppress(ValueError, io.UnsupportedOperation):
                stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    _ensure_utf8_streams()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_PATH,
        help="protocol markdown to score (default: docs/experiments/distribution-five-reader.md)",
    )
    parser.add_argument("--check", action="store_true", help="exit 1 if rows or headline disagree")
    args = parser.parse_args(argv)
    try:
        report = parse_register(args.path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"cannot read register: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    return int(args.check and bool(report.errors))


if __name__ == "__main__":
    raise SystemExit(main())
