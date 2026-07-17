"""Language 0.3: `parse: list` and raw whole-template input resolution."""

import pytest

from mklang.engine import _parse_list, run
from mklang.interpolate import resolve
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM
from mklang.loader import semantic_check
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def test_parse_list_plain_and_fenced():
    assert _parse_list('["a", "b"]') == ["a", "b"]
    assert _parse_list('```json\n["a", 2]\n```') == ["a", 2]
    assert _parse_list("  [1, 2, 3]  ") == [1, 2, 3]


def test_parse_list_rejects_non_arrays():
    with pytest.raises(ValueError, match="parse-list"):
        _parse_list("step one, then two")
    with pytest.raises(ValueError, match="not an array"):
        _parse_list('{"a": 1}')


def test_resolve_whole_template_passes_raw_values():
    ctx = {"items": ["x", "y"], "n": 3, "name": "ada"}
    assert resolve("{{items}}", ctx) == ["x", "y"]
    assert resolve(" {{ n }} ", ctx) == 3
    assert resolve("hi {{name}}", ctx) == "hi ada"  # mixed template stays a string
    assert resolve("{{missing}}", ctx) == ""
    assert resolve(7, ctx) == 7  # non-string YAML values pass through
    assert resolve(None, ctx) == ""


def test_parse_failure_halts_cleanly():
    m = parse_machine(
        {
            "mklang": "0.3",
            "machine": "p",
            "entry": "plan",
            "budget": 3,
            "states": {
                "plan": {
                    "structure": "s",
                    "prompt": "plan it",
                    "parse": "list",
                    "output": "steps",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    llm = MockLLM(produce_fn=lambda *a: Produced(text="not json"))
    res = run(m, {}, {m.name: m}, llm, TIERS, "m")
    assert res.status == "halt"
    assert res.error.startswith("state-error: parse-list")
    assert res.at == "plan"


def test_semantic_check_warns_parse_on_02_document():
    m = parse_machine(
        {
            "mklang": "0.2",
            "machine": "p",
            "entry": "s",
            "budget": 3,
            "states": {
                "s": {
                    "structure": "s",
                    "prompt": "p",
                    "parse": "list",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    errors, warnings = semantic_check(m, {m.name: m})
    assert errors == []
    assert any("0.3 face" in w for w in warnings)


def test_version_03_is_supported_strict():
    m = parse_machine(
        {
            "mklang": "0.3",
            "machine": "v",
            "entry": "s",
            "budget": 3,
            "states": {
                "s": {
                    "structure": "s",
                    "prompt": "p",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                }
            },
        }
    )
    errors, warnings = semantic_check(m, {m.name: m}, strict=True)
    assert errors == [] and warnings == []
