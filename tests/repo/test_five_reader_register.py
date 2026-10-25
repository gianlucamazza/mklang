"""Synthetic scoring fixtures only; no human sessions or results."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from conftest import REPO_ROOT

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DOC = REPO_ROOT / "docs/experiments/distribution-five-reader.md"
SCRIPT = REPO_ROOT / "scripts/five_reader_register.py"
needs_doc = pytest.mark.skipif(not DOC.is_file(), reason="protocol absent (sdist build)")
pytestmark = pytest.mark.skipif(not SCRIPT.is_file(), reason="script absent (sdist build)")


def _scorer():
    from scripts import five_reader_register

    return five_reader_register


def _synthetic(answers, installs, headline=None):
    """Clearly synthetic readers and questions, never experimental evidence."""
    scorer = _scorer()
    lines = [
        "# Synthetic fixture",
        "## Results register",
        "| # | Venue/role | First question | Understood | Tried |",
        "| --- | --- | --- | --- | --- |",
    ]
    for i, (answer, install) in enumerate(zip(answers, installs, strict=True), 1):
        if answer is None:
            lines.append(f"| {i} | _pending_ | | | |")
        else:
            role = f"synthetic reader {chr(64 + i)}"
            lines.append(f"| {i} | {role} | synthetic question {i} | {answer} | {install} |")
    lines.append(f"{scorer.HEADLINE_PREFIX} _{headline or scorer.PLACEHOLDER}_")
    return "\n".join(lines)


@needs_doc
def test_real_doc_pending(capsys):
    scorer = _scorer()
    report = scorer.parse_register(DOC.read_text(encoding="utf-8"))
    assert report.status == "pending"
    assert report.errors == []
    assert report.counts is None
    assert scorer.main(["--check"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pending"


@pytest.mark.parametrize(
    ("answers", "installs", "branch", "totals"),
    [
        (["no"] * 5, ["no"] * 5, "positioning problem", (0, 0)),
        (["yes"] * 5, ["NO"] * 5, "best use absent from the pitch", (5, 0)),
        (["YES"] * 5, ["yes"] + ["no"] * 4, "distribution working", (5, 1)),
        (["yes"] * 5, [""] + ["no"] * 4, None, (5, 0)),
        (["no"] * 3 + ["yes"] * 2, ["yes"] * 5, "positioning problem", (2, 5)),
    ],
)
def test_synthetic_branches(answers, installs, branch, totals):
    understood, tried = totals
    expected = f"{understood}/5 understood · {tried}/5 tried · branch: {branch or '—'}"
    report = _scorer().parse_register(_synthetic(answers, installs, expected))
    assert report.status == "complete"
    assert report.errors == []
    assert report.branch == branch
    assert report.expected_headline == expected
    assert report.counts.understood == understood
    assert report.counts.not_understood == 5 - understood
    assert report.counts.tried == tried
    assert report.counts.tried_unchecked == installs.count("")


def test_synthetic_partial():
    scorer = _scorer()
    report = scorer.parse_register(_synthetic(["yes"] + [None] * 4, ["no"] * 5))
    assert report.status == "partial"
    assert report.expected_headline == scorer.PLACEHOLDER
    assert report.errors == []
    assert report.counts is None
    assert report.branch is None


def test_synthetic_pending_cells():
    scorer = _scorer()
    text = _synthetic([None] * 5, [""] * 5)
    text = text.replace("| _pending_ | | | |", "| _pending_ | _pending_ | _pending_ | _pending_ |")
    report = scorer.parse_register(text)
    assert report.status == "pending"
    assert report.errors == []


@pytest.mark.parametrize(
    ("answers", "installs", "error"),
    [
        (["yes", "maybe"] + ["yes"] * 3, ["no"] * 5, "row 2: understood must be yes or no"),
        (["yes"] * 4, ["no"] * 4, "exactly 5 rows numbered 1..5"),
        (["yes"] * 5, ["maybe"] * 5, "row 1: tried must be yes, no or empty"),
    ],
)
def test_synthetic_invalid(answers, installs, error):
    report = _scorer().parse_register(_synthetic(answers, installs))
    assert report.status == "invalid"
    assert any(error in message for message in report.errors)
    assert report.counts is None
    assert report.branch is None


def test_synthetic_wrong_headline():
    report = _scorer().parse_register(_synthetic(["yes"] * 5, ["no"] * 5))
    assert report.status == "complete"
    expected = "5/5 understood · 0/5 tried · branch: best use absent from the pitch"
    line = f"paste this line: **Headline (fill after run):** _{expected}_"
    assert any(line in error for error in report.errors)


def test_synthetic_missing_fields_and_wrong_numbers():
    text = _synthetic(["yes"] * 5, ["no"] * 5)
    text = text.replace("| 2 | synthetic reader B | synthetic question 2 |", "| 1 | | |")
    report = _scorer().parse_register(text)
    assert "row 1: venue must be non-empty" in report.errors
    assert "row 1: question must be non-empty" in report.errors
    assert any("numbered 1..5" in error for error in report.errors)


@needs_doc
def test_cli_check(tmp_path):
    invalid = tmp_path / "synthetic.md"
    invalid.write_text(_synthetic(["maybe"] * 5, ["no"] * 5), encoding="utf-8")
    for path, expected_code in [(invalid, 1), (DOC, 0)]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check", "--path", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == expected_code, result.stderr
        assert bool(json.loads(result.stdout)["errors"]) == bool(expected_code)


def test_cli_exit_codes(tmp_path, capsys):
    scorer = _scorer()
    path = tmp_path / "synthetic.md"
    path.write_text(_synthetic(["maybe"] * 5, ["no"] * 5), encoding="utf-8")
    assert scorer.main(["--path", str(path)]) == 0
    path.write_text("no table", encoding="utf-8")
    assert scorer.main(["--path", str(path)]) == 2
    assert "missing Results register" in capsys.readouterr().err
    path.unlink()
    assert scorer.main(["--path", str(path)]) == 2


def test_synthetic_escaped_pipe_stays_in_the_question():
    scorer = _scorer()
    expected = "5/5 understood · 0/5 tried · branch: best use absent from the pitch"
    text = _synthetic(["yes"] * 5, ["no"] * 5, expected)
    text = text.replace("synthetic question 3", r"synthetic question a \| b")
    report = scorer.parse_register(text)
    assert report.errors == []
    assert report.rows[2].question == "synthetic question a | b"
