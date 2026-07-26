"""Context rendering budgets (ADR 0017 — judge path)."""

from mklang.llm.context_view import format_judge_context


def test_format_judge_context_complete_when_small():
    ctx = {"a": 1, "b": "x"}
    s = format_judge_context(ctx, 4000)
    assert '"a": 1' in s
    assert "context_truncated" not in s


def test_format_judge_context_marks_middle_when_over_budget():
    ctx = {"blob": "x" * 5000}
    s = format_judge_context(ctx, 200)
    assert "context_truncated" in s
    assert len(s) <= 200
    assert s.startswith("{")
    assert s.endswith("}")
