"""The host seam (host.py): prepare_path / prepare_source / build_output / set_path."""

import pytest

from mklang import host
from mklang.engine import RunResult, run
from mklang.llm.base import Produced
from mklang.llm.mock import MockLLM

CONFIG = "config/runtime.example.yaml"

INLINE = """\
machine: inline
entry: s1
budget: 3
result: answer
context:
  q: "why?"
states:
  s1:
    structure: one line
    prompt: "answer: {{q}}"
    output: answer
    gates:
      - when: otherwise
        then: ok
        to: END
"""

CALLER = """\
machine: caller
entry: c1
budget: 5
states:
  c1:
    call: worker
    output: sub
    gates:
      - when: otherwise
        then: ok
        to: END
"""

WORKER = """\
machine: worker
entry: w1
budget: 3
result: out
states:
  w1:
    structure: one line
    prompt: "do the work"
    output: out
    gates:
      - when: otherwise
        then: ok
        to: END
"""


def mock_llm():
    return MockLLM(produce_fn=lambda model, system, user, reason: Produced(text=user))


def build_llm(prov):
    return mock_llm()


def test_prepare_source_happy_path():
    p = host.prepare_source(CONFIG, None, INLINE, build_llm=build_llm)
    assert p.machine.name == "inline"
    assert p.registry["inline"] is p.machine
    assert all(n == "inline" or n.startswith("std_") for n in p.registry)
    assert isinstance(p.tools, dict) and isinstance(p.hooks, dict)
    res = run(p.machine, dict(p.machine.context), p.registry, p.llm, p.prov.tiers)
    assert res.status == "done"
    assert "why?" in res.result


def test_prepare_source_invalid_yaml():
    with pytest.raises(host.PrepareError) as ei:
        host.prepare_source(CONFIG, None, "states: [unclosed", build_llm=build_llm)
    assert ei.value.kind == "load"
    assert "invalid YAML" in ei.value.errors[0]


def test_prepare_source_not_a_mapping():
    with pytest.raises(host.PrepareError) as ei:
        host.prepare_source(CONFIG, None, "just a string", build_llm=build_llm)
    assert ei.value.kind == "load"
    assert "not a mapping" in ei.value.errors[0]


def test_prepare_source_schema_violation():
    no_budget = INLINE.replace("budget: 3\n", "")
    with pytest.raises(host.PrepareError) as ei:
        host.prepare_source(CONFIG, None, no_budget, build_llm=build_llm)
    assert ei.value.kind == "load"
    assert ei.value.errors[0].startswith("schema:")


def test_prepare_source_call_to_unsupplied_target_is_semantic_error():
    with pytest.raises(host.PrepareError) as ei:
        host.prepare_source(CONFIG, None, CALLER, build_llm=build_llm)
    assert ei.value.kind == "semantic"
    assert any("unknown machine 'worker'" in e for e in ei.value.errors)


def test_prepare_path_discovers_sibling_registry(tmp_path):
    (tmp_path / "caller.mk").write_text(CALLER, encoding="utf-8")
    (tmp_path / "worker.mk").write_text(WORKER, encoding="utf-8")
    p = host.prepare_path(CONFIG, None, str(tmp_path / "caller.mk"), build_llm=build_llm)
    assert {"caller", "worker"} <= set(p.registry)  # stdlib machines ride along


def test_prepare_path_load_failure(tmp_path):
    bad = tmp_path / "bad.mk"
    bad.write_text("machine: x\n", encoding="utf-8")  # missing entry/budget/states
    with pytest.raises(host.PrepareError) as ei:
        host.prepare_path(CONFIG, None, str(bad), build_llm=build_llm)
    assert ei.value.kind == "load"


def test_build_output_shape():
    res = RunResult(status="done", trace=[], context={}, result="r", usage={"input_tokens": 1})
    out = host.build_output(res)
    assert out == {
        "status": "done",
        "error": None,
        "result": "r",
        "usage": {"input_tokens": 1},
        "trace": [],
    }
    assert "at" not in out
    sus = RunResult(status="suspended", trace=[], context={}, error="escalated", at="review")
    assert host.build_output(sus)["at"] == "review"


def test_set_path_nested_creation():
    ctx = {"a": 1}
    host.set_path(ctx, "human.reply", "approve")
    host.set_path(ctx, "a", 2)
    assert ctx == {"a": 2, "human": {"reply": "approve"}}
    # a non-dict intermediate is replaced, matching --set semantics
    host.set_path(ctx, "a.b", 3)
    assert ctx["a"] == {"b": 3}


def test_inject_host_defaults_today_only_when_declared():
    bare = {"q": "x"}
    host.inject_host_defaults(bare)
    assert "today" not in bare

    empty = {"today": "", "q": "x"}
    host.inject_host_defaults(empty, today="2026-07-17")
    assert empty["today"] == "2026-07-17"

    kept = {"today": "2099-01-01"}
    host.inject_host_defaults(kept, today="2026-07-17")
    assert kept["today"] == "2099-01-01"  # user/host override wins


def test_compact_run_observation_honesty():
    res = RunResult(
        "done",
        [{"state": "a", "truncated": True, "finish_reason": "length", "output": "cut"}],
        {},
        result="R" * 2500,
    )
    out = host.compact_run_observation(res)
    assert out["truncated"] is True
    assert out["finish_reason"] == "length"
    assert out["trace"] == {
        "steps": 1,
        "truncated": True,
        "truncated_steps": [{"state": "a", "finish_reason": "length"}],
    }
    assert out["result_truncated"] is True
    assert out["result"].endswith("…[truncated]")
    assert out["result_full_chars"] == 2500
