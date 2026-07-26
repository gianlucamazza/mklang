"""Tests for the shared scripted-test harness (`mklang.scripttest`) and the
`mklang test` CLI that consumes it."""

from __future__ import annotations

from pathlib import Path

from mklang.cli import main
from mklang.model import parse_machine
from mklang.scripttest import Mismatch, match_expectation, run_scenario

_MACHINE = {
    "machine": "gate",
    "entry": "s",
    "budget": 3,
    "states": {
        "s": {
            "structure": "x",
            "prompt": "p",
            "output": "o",
            "gates": [
                {"when": "the output is good", "then": "ok", "to": "END"},
                {"when": "otherwise", "then": "ok", "to": "END"},
            ],
        }
    },
}


def test_run_scenario_and_matcher_pass():
    m = parse_machine(_MACHINE)
    r = run_scenario(m, {m.name: m}, {"llm": {"produce": ["hi"], "judge": [0]}})
    assert not match_expectation(r, {"status": "done", "trace": [{"state": "s", "to": "END"}]})


def test_matcher_reports_first_mismatched_key_readably():
    m = parse_machine(_MACHINE)
    r = run_scenario(m, {m.name: m}, {"llm": {"produce": ["hi"], "judge": [0]}})
    mismatches = match_expectation(r, {"status": "halt"})
    assert mismatches == [Mismatch("status", "halt", "done")]
    # The rendered diff names the key with expected vs actual.
    assert str(mismatches[0]) == "status: expected 'halt', got 'done'"


def test_matcher_trace_length_mismatch():
    m = parse_machine(_MACHINE)
    r = run_scenario(m, {m.name: m}, {"llm": {"produce": ["hi"], "judge": [0]}})
    ms = match_expectation(r, {"status": "done", "trace": [{"state": "s"}, {"state": "s"}]})
    assert ms and ms[0].key == "trace.length"


def _write(tmp_path: Path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


_MK = """
mklang: "0.2"
machine: gate
entry: s
budget: 3
states:
  s:
    structure: x
    prompt: p
    output: o
    gates:
      - { when: the output is good, then: ok, to: END }
      - { when: otherwise, then: ok, to: END }
"""


def test_cli_test_passes(tmp_path, capsys):
    mk = _write(tmp_path, "gate.mkl", _MK)
    script = _write(
        tmp_path,
        "gate.test.yaml",
        """
scenarios:
  - name: ok-path
    llm: { produce: ["hi"], judge: [0] }
    expect: { status: done }
""",
    )
    rc = main(["test", mk, "--script", script])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PASS ok-path" in out


def test_cli_test_wrong_expect_fails_with_readable_diff(tmp_path, capsys):
    mk = _write(tmp_path, "gate.mkl", _MK)
    script = _write(
        tmp_path,
        "gate.test.yaml",
        """
scenarios:
  - name: deliberately-wrong
    llm: { produce: ["hi"], judge: [0] }
    expect: { status: halt, error: gate-fail }
""",
    )
    rc = main(["test", mk, "--script", script])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL deliberately-wrong" in out
    # Minimal diff: the first mismatched key with expected vs actual.
    assert "status: expected 'halt', got 'done'" in out


def test_cli_test_missing_scenarios_key(tmp_path):
    mk = _write(tmp_path, "gate.mkl", _MK)
    script = _write(tmp_path, "empty.test.yaml", "notscenarios: []\n")
    assert main(["test", mk, "--script", script]) == 2
