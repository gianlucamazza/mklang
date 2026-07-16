"""Semantic checks and the schema drift guard."""

import json
from pathlib import Path

from mklang.loader import _schema, semantic_check
from mklang.model import parse_machine


def mk(d):
    return parse_machine(d)


def test_semantic_check_flags_call_dead_and_result():
    parent = mk(
        {
            "machine": "p",
            "entry": "a",
            "budget": 5,
            "result": "missing",
            "states": {
                "a": {
                    "call": "nope",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
                "dead": {
                    "structure": "x",
                    "prompt": "p",
                    "output": "o2",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    errors, warnings = semantic_check(parent, {"p": parent})
    assert any("unknown machine 'nope'" in e for e in errors)
    assert any("dead" in w and "unreachable" in w for w in warnings)
    assert any("result key 'missing'" in w for w in warnings)


def test_single_gate_terminal_does_not_warn_catchall():
    m = mk(
        {
            "machine": "t",
            "entry": "a",
            "budget": 3,
            "states": {
                "a": {
                    "structure": "x",
                    "prompt": "p",
                    "output": "o",
                    "gates": [{"when": "the work is done", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    _, warnings = semantic_check(m, {"t": m})
    assert not any("catch-all" in w for w in warnings)


def test_load_registry_skips_malformed_siblings(tmp_path):
    from mklang.registry import load_registry

    (tmp_path / "good.mk").write_text(
        "machine: g\nentry: a\nbudget: 3\nstates:\n"
        "  a: {structure: x, prompt: p, output: o, gates: [{when: otherwise, then: ok, to: END}]}\n"
    )
    (tmp_path / "broken.mk").write_text("machine: b\nstates: {a: {}}\n")  # no output/gates
    reg = load_registry(tmp_path, validate=False)
    assert set(reg) == {"g"}


def test_bundled_schema_matches_repo_root():
    root = json.loads(Path("schema/mklang.schema.json").read_text(encoding="utf-8"))
    assert _schema() == root


def test_check_tiers_flags_missing():
    from mklang.loader import check_tiers, used_tiers

    m = mk(
        {
            "machine": "t",
            "entry": "a",
            "budget": 3,
            "default_tier": "balanced",
            "states": {
                "a": {
                    "structure": "x",
                    "prompt": "p",
                    "tier": "reasoning",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )
    assert used_tiers(m) == {"balanced", "reasoning"}
    assert check_tiers(m, {"fast": "m", "balanced": "m"})  # missing reasoning
    assert not check_tiers(m, {"fast": "m", "balanced": "m", "reasoning": "m"})
