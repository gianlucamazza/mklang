"""Static-analysis findings from mklang.lint (advisory, never blocking)."""

from mklang.lint import lint_machine
from mklang.model import parse_machine


def M(states, **kw):
    return parse_machine(
        {"machine": "m", "entry": next(iter(states)), "budget": 5, "states": states, **kw}
    )


def gate(when, **kw):
    return {"when": when, **kw}


def state(prompt="p", output="o", gates=None):
    return {
        "structure": "s",
        "prompt": prompt,
        "output": output,
        "gates": gates or [gate("otherwise", then="ok", to="END")],
    }


def test_dead_gates_after_otherwise():
    m = M(
        {
            "a": state(
                gates=[
                    gate("otherwise", then="ok", to="END"),
                    gate("never", then="ok", to="END"),
                ]
            )
        }
    )
    assert any("after 'otherwise'" in f for f in lint_machine(m))


def test_repair_only_state():
    m = M(
        {
            "a": state(gates=[gate("fix", repair=2, to="a")]),
        }
    )
    assert any("every gate is a repair" in f for f in lint_machine(m))


def test_unread_output_flagged_but_not_terminal_or_judged():
    m = M(
        {
            "a": state(output="orphan", gates=[gate("otherwise", then="ok", to="b")]),
            "b": state(output="final"),
        }
    )
    findings = lint_machine(m)
    assert any("'orphan' is never read" in f for f in findings)
    assert not any("'final'" in f for f in findings)  # terminal exemption

    judged = M(
        {
            "a": state(
                output="verdict",
                gates=[
                    gate("the verdict is sufficient", then="ok", to="b"),
                    gate("otherwise", then="ok", to="b"),
                ],
            ),
            "b": state(output="final"),
        }
    )
    assert not any("'verdict'" in f for f in lint_machine(judged))  # judge consumes it


def test_template_typo_root():
    m = M(
        {
            "a": state(prompt="use {{qestion.text}}", output="o"),
        },
        context={"question": {"text": "hi"}},
    )
    findings = lint_machine(m)
    assert any("qestion" in f for f in findings)
    # A valid dotted path (first segment in context) is not flagged.
    ok_dotted = M(
        {"a": state(prompt="use {{question.text}}", output="o")},
        context={"question": {"text": "hi"}},
    )
    assert not any("question" in f for f in lint_machine(ok_dotted))
    # The HITL resume root `human` is always allowable, never flagged.
    ok_human = M({"a": state(prompt="reply {{human.reply}}", output="o")})
    assert not any("human" in f for f in lint_machine(ok_human))


def test_output_produced_key_not_flagged():
    """A key produced by an earlier state's output is a valid reference (F7)."""
    m = M(
        {
            "a": state(output="draft", gates=[gate("otherwise", then="ok", to="b")]),
            "b": state(prompt="polish {{draft}}", output="final"),
        }
    )
    assert not any("unresolved" in f.lower() or "draft" in f for f in lint_machine(m))


def test_dotted_second_segment_on_inline_context_map():
    """Second path segment is checked against an inline context map's keys (R3-3)."""
    ctx = {"ticket": {"body": "hi"}}
    # A typo in the second segment is flagged...
    bad = M({"a": state(prompt="reads {{ticket.bod}}", output="o")}, context=ctx)
    findings = lint_machine(bad)
    assert any("ticket.bod" in f and "has no key 'bod'" in f for f in findings)
    # ...but the correct key is not.
    ok = M({"a": state(prompt="reads {{ticket.body}}", output="o")}, context=ctx)
    assert not any("ticket" in f for f in lint_machine(ok))


def test_dotted_second_segment_skips_state_outputs_and_runtime_roots():
    """State outputs and runtime roots have unknowable shape — segment 2 is skipped."""
    # `draft` is a state output, not an inline map: `{{draft.foo}}` must NOT be flagged.
    m = M(
        {
            "a": state(output="draft", gates=[gate("otherwise", then="ok", to="b")]),
            "b": state(prompt="polish {{draft.foo}}", output="final"),
        }
    )
    assert not any("draft" in f for f in lint_machine(m))
    # The HITL `human` resume root: `{{human.reply}}` is never flagged on segment 2.
    ok_human = M({"a": state(prompt="reply {{human.reply}}", output="o")})
    assert not any("human" in f for f in lint_machine(ok_human))


def test_fanout_vars_outside_fanout_flagged():
    """`item`/`index` in a non-fan-out state is an authoring mistake (F7)."""
    bad = M({"a": state(prompt="branch {{index}}", output="o")})
    findings = lint_machine(bad)
    assert any("index" in f and "fan-out" in f for f in findings)

    # Inside a fan-out (sample) state, {{index}} is valid and not flagged.
    ok_sample = parse_machine(
        {
            "machine": "m",
            "entry": "a",
            "budget": 5,
            "states": {
                "a": {
                    "structure": "s",
                    "prompt": "branch {{index}}",
                    "sample": 3,
                    "output": "o",
                    "gates": [gate("otherwise", then="ok", to="END")],
                }
            },
        }
    )
    assert not any("index" in f for f in lint_machine(ok_sample))
