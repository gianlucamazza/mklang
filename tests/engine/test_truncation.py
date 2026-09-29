"""Output anti-cutoff (ADR 0018): detect, annotate, optional halt."""

from mklang.engine import run
from mklang.llm.base import Produced, is_length_stop
from mklang.llm.mock import MockLLM
from mklang.model import parse_machine

TIERS = {"fast": "m", "balanced": "m", "reasoning": "m"}


def _m():
    return parse_machine(
        {
            "machine": "t",
            "entry": "a",
            "budget": 5,
            "result": "o",
            "states": {
                "a": {
                    "structure": "text",
                    "prompt": "write something long",
                    "output": "o",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )


def test_is_length_stop_normalizes_providers():
    assert is_length_stop("length")
    assert is_length_stop("max_tokens")
    assert is_length_stop("MAX_TOKENS")
    assert not is_length_stop("stop")
    assert not is_length_stop(None)


def test_report_annotates_trace_and_continues():
    m = _m()

    def produce(model, system, user, reason=False):
        return Produced(
            text="partial answer that was cut",
            truncated=True,
            finish_reason="length",
            input_tokens=3,
            output_tokens=2,
        )

    r = run(m, {}, {m.name: m}, MockLLM(produce_fn=produce), TIERS, on_truncate="report")
    assert r.status == "done"
    assert r.result == "partial answer that was cut"
    assert r.trace[0].get("truncated") is True
    assert r.trace[0].get("finish_reason") == "length"


def test_halt_policy_stops_with_output_truncated():
    m = _m()

    def produce(model, system, user, reason=False):
        return Produced(text="cut", truncated=True, finish_reason="max_tokens")

    r = run(m, {}, {m.name: m}, MockLLM(produce_fn=produce), TIERS, on_truncate="halt")
    assert r.status == "halt"
    assert r.error == "state-error: output-truncated"
    assert r.at == "a"


def test_parse_list_truncated_is_labeled():
    m = parse_machine(
        {
            "machine": "t",
            "entry": "a",
            "budget": 5,
            "mklang": "0.3",
            "states": {
                "a": {
                    "structure": "JSON array",
                    "prompt": "list steps",
                    "parse": "list",
                    "output": "steps",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        }
    )

    def produce(model, system, user, reason=False):
        return Produced(text='["one", "tw', truncated=True, finish_reason="length")

    r = run(m, {}, {m.name: m}, MockLLM(produce_fn=produce), TIERS, on_truncate="report")
    assert r.status == "halt"
    assert r.error == "state-error: parse-list-truncated"


def test_complete_produce_has_no_truncated_flag():
    m = _m()
    r = run(
        m,
        {},
        {m.name: m},
        MockLLM(produce_fn=lambda *a: Produced(text="full")),
        TIERS,
    )
    assert r.status == "done"
    assert "truncated" not in r.trace[0]


def test_openai_compat_length_finish_reason():
    """Adapter maps choices[0].finish_reason=length → Produced.truncated (no network)."""
    from mklang.llm.openai_compat import OpenAICompatLLM, OpenAICompatProfile

    class _Msg:
        content = "partial"
        reasoning_content = None

    class _Choice:
        message = _Msg()
        finish_reason = "length"

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 2

    class _Resp:
        def __init__(self):
            self.choices = [_Choice()]
            self.usage = _Usage()

    llm = OpenAICompatLLM.__new__(OpenAICompatLLM)
    llm.max_retries = 0
    llm.client = type(
        "C",
        (),
        {
            "chat": type(
                "Ch",
                (),
                {"completions": type("Co", (), {"create": staticmethod(lambda **k: _Resp())})()},
            )()
        },
    )()
    llm.profile = OpenAICompatProfile()
    p = llm.produce("m", "sys", "user")
    assert p.truncated is True
    assert p.finish_reason == "length"
    assert p.text == "partial"


def _billed(text, *, truncated=False):
    def produce(model, system, user, reason=False):
        return Produced(
            text=text,
            truncated=truncated,
            finish_reason="length" if truncated else "stop",
            input_tokens=1200,
            output_tokens=4096,
        )

    return MockLLM(produce_fn=produce)


def _parse_machine(parse, *, sample=None):
    state = {
        "structure": "JSON",
        "prompt": "emit it",
        "parse": parse,
        "output": "o",
        "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
    }
    if sample:
        state["sample"] = sample
    return parse_machine(
        {"machine": "t", "entry": "a", "budget": 5, "mklang": "0.4", "states": {"a": state}}
    )


def test_halt_on_truncation_still_charges_the_call():
    """A truncated answer the policy refuses was produced and paid for: the halt
    keeps its reason but the tokens reach usage and the step's cost."""
    m = _m()
    r = run(m, {}, {m.name: m}, _billed("cut", truncated=True), TIERS, on_truncate="halt")
    assert (r.status, r.error) == ("halt", "state-error: output-truncated")
    assert r.usage == {"input_tokens": 1200, "output_tokens": 4096}
    assert r.trace[-1]["state"] == "a"
    assert r.trace[-1]["cost"] == {"input_tokens": 1200, "output_tokens": 4096}


def test_parse_truncated_halt_still_charges_the_call():
    m = _parse_machine("list")
    r = run(m, {}, {m.name: m}, _billed('["one", "tw', truncated=True), TIERS)
    assert (r.status, r.error) == ("halt", "state-error: parse-list-truncated")
    assert r.usage == {"input_tokens": 1200, "output_tokens": 4096}


def test_unparseable_output_halt_still_charges_the_call():
    m = _parse_machine("json")
    r = run(m, {}, {m.name: m}, _billed("not json at all"), TIERS)
    assert r.status == "halt"
    assert (r.error or "").startswith("state-error: parse-json: output is not valid JSON (")
    assert r.usage == {"input_tokens": 1200, "output_tokens": 4096}
    assert r.trace[-1]["cost"] == {"input_tokens": 1200, "output_tokens": 4096}


def test_refused_branch_keeps_its_tokens():
    """A fan-out branch whose answer is refused becomes a marker, like a failed
    call, and its tokens still count toward the step."""
    m = _parse_machine("json", sample=2)
    r = run(m, {}, {m.name: m}, _billed("not json"), TIERS)
    assert r.status == "done"
    assert all(str(b).startswith("[branch-error: parse-json: ") for b in r.result)
    assert r.usage == {"input_tokens": 2400, "output_tokens": 8192}
