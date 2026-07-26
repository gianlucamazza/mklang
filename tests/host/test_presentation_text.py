"""Human-first text emitters (ADR 0022): run and machines rendering, offline."""

from mklang.presentation import emit_machines_text, emit_run_text


def test_emit_run_text_done_with_result_and_usage(capsys):
    emit_run_text(
        {
            "status": "done",
            "result": "42",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "trace": [{"state": "a"}, {"state": "b"}],
        },
        machine="calc",
        provider="deepseek",
        color="never",
    )
    out = capsys.readouterr().out
    assert "DONE" in out and "calc" in out and "deepseek" in out
    assert "42" in out
    assert "tokens 10+5" in out and "steps 2" in out


def test_emit_run_text_halt_shows_error(capsys):
    emit_run_text(
        {"status": "halt", "error": "gate-fail", "trace": []},
        machine="m",
        provider="p",
        color="never",
    )
    out = capsys.readouterr().out
    assert "HALT" in out and "gate-fail" in out


def test_emit_run_text_suspended_shows_checkpoint(capsys):
    emit_run_text(
        {"status": "suspended", "error": "escalated", "checkpoint": "/tmp/ck.json", "trace": []},
        machine="m",
        provider="p",
        color="never",
    )
    out = capsys.readouterr().out
    assert "SUSPENDED" in out and "/tmp/ck.json" in out


def test_emit_machines_text_table(capsys):
    emit_machines_text(
        [
            {
                "name": "std_cot",
                "source": "stdlib",
                "entry": "solve",
                "result": "answer",
                "budget": 4,
                "context": {"task": ""},
            },
            {"name": "bare", "source": "user", "entry": "a", "budget": 2, "context": {}},
        ],
        color="never",
    )
    out = capsys.readouterr().out
    assert "std_cot" in out and "stdlib" in out and "task" in out
    # missing result / empty context render as placeholders, not blanks
    assert "—" in out
