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
    # runtime roots never flagged
    ok = M({"a": state(prompt="reply {{human.reply}} on {{item}}", output="o")})
    assert not any("human" in f or "item" in f for f in lint_machine(ok))
