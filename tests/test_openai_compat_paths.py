"""OpenAI-compat adapter: produce/judge/params paths — offline fakes, no network."""

import re

import pytest

from mklang.errors import JudgeUnparseable, ProviderError
from mklang.llm.openai_compat import (
    OpenAICompatLLM,
    _apply_params,
    _drop_offending_param,
    _usage,
)


class _Msg:
    def __init__(self, content="ok", reasoning_content=None):
        self.content = content
        self.reasoning_content = reasoning_content


class _Choice:
    def __init__(self, msg, finish_reason="stop"):
        self.message = msg
        self.finish_reason = finish_reason


class _Usage:
    def __init__(self, prompt=3, completion=7):
        self.prompt_tokens = prompt
        self.completion_tokens = completion


class _Resp:
    def __init__(self, content="ok", finish="stop", reasoning=None, usage=True):
        self.choices = [_Choice(_Msg(content, reasoning), finish)]
        self.usage = _Usage() if usage else None


class _Completions:
    def __init__(self, side_effect):
        self.calls = []
        self._side_effect = side_effect

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self._side_effect(len(self.calls), kwargs)


def _adapter(side_effect, max_retries=3):
    llm = OpenAICompatLLM.__new__(OpenAICompatLLM)
    llm.max_retries = max_retries
    completions = _Completions(side_effect)
    llm.client = type("C", (), {"chat": type("Ch", (), {"completions": completions})()})()
    return llm, completions


# ------------------------------------------------------------------- produce


def test_produce_maps_response_and_defaults_max_tokens():
    llm, completions = _adapter(lambda n, k: _Resp(content=" hi "))
    p = llm.produce("m", "sys", "usr")
    assert p.text == "hi"
    assert (p.input_tokens, p.output_tokens) == (3, 7)
    assert p.truncated is False and p.finish_reason == "stop"
    sent = completions.calls[0]
    assert sent["max_tokens"] == 4096  # ADR 0018 explicit budget
    assert sent["messages"][0]["role"] == "system"


def test_produce_marks_length_stop_as_truncated():
    llm, _ = _adapter(lambda n, k: _Resp(finish="length"))
    p = llm.produce("m", "sys", "usr")
    assert p.truncated is True and p.finish_reason == "length"


def test_produce_reasoning_only_when_requested():
    llm, _ = _adapter(lambda n, k: _Resp(reasoning="thought"))
    assert llm.produce("m", "s", "u", reason=True).reasoning == "thought"
    assert llm.produce("m", "s", "u", reason=False).reasoning is None


def test_produce_splits_params_and_forwards_openai_thinking():
    llm, completions = _adapter(lambda n, k: _Resp())
    llm.produce(
        "m",
        "s",
        "u",
        params={"reasoning_effort": "high", "custom": 1, "thinking": {"type": "enabled"}},
    )
    sent = completions.calls[0]
    assert sent["reasoning_effort"] == "high"  # SDK top-level
    assert sent["extra_body"] == {"custom": 1, "thinking": {"type": "enabled"}}
    assert "temperature" not in sent


def test_produce_forwards_disabled_thinking_and_keeps_temperature():
    llm, completions = _adapter(lambda n, k: _Resp())
    llm.produce("m", "s", "u", params={"thinking": {"type": "disabled"}})
    sent = completions.calls[0]
    assert sent["temperature"] == 0.4
    assert sent["extra_body"] == {"thinking": {"type": "disabled"}}


# -------------------------------------------------------- _create resilience


def test_create_drops_rejected_param_and_retries_once():
    def side_effect(n, kwargs):
        if n == 1:
            raise RuntimeError("unsupported parameter: temperature")
        return _Resp()

    llm, completions = _adapter(side_effect)
    p = llm.produce("m", "s", "u")
    assert p.text == "ok"
    assert len(completions.calls) == 2
    assert "temperature" not in completions.calls[1]


def test_create_drops_rejected_extra_body_key():
    def side_effect(n, kwargs):
        if n == 1:
            raise RuntimeError("unknown field: custom")
        return _Resp()

    llm, completions = _adapter(side_effect)
    llm.produce("m", "s", "u", params={"custom": 1})
    assert "extra_body" not in completions.calls[1]


def test_create_raises_provider_error_when_nothing_droppable():
    def side_effect(n, kwargs):
        raise RuntimeError("bad request: model not found")

    llm, _ = _adapter(side_effect)
    with pytest.raises(ProviderError):
        llm.produce("m", "s", "u")


def test_model_not_found_error_names_the_configured_model():
    def side_effect(n, kwargs):
        raise RuntimeError("model not found")

    llm, _ = _adapter(side_effect)
    with pytest.raises(ProviderError, match="configured model='deepseek-v4-flash'"):
        llm.produce("deepseek-v4-flash", "s", "u")


# --------------------------------------------------------------------- judge


def test_judge_fences_data_and_parses_choice():
    captured = {}

    def side_effect(n, kwargs):
        captured.update(kwargs)
        return _Resp(content='{"choice": 2}')

    llm, _ = _adapter(side_effect)
    idx, method = llm.judge("m", ["a", "b"], "out", {"k": 1}, reasoning="why")
    assert (idx, method) == (1, "json")
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    body = captured["messages"][1]["content"]
    # OUTPUT/REASONING/CONTEXT ride fences (ADR 0025); conditions stay bare.
    assert re.search(r"OUTPUT:\n<data-\w+>\nout\n</data-\w+>", body)
    assert re.search(r"REASONING:\n<data-\w+>\nwhy\n</data-\w+>", body)
    assert "1. a" in body and "2. b" in body


def test_judge_unparseable_raises():
    llm, _ = _adapter(lambda n, k: _Resp(content="no numbers here"))
    with pytest.raises(JudgeUnparseable):
        llm.judge("m", ["a", "b"], "out", {})


# ------------------------------------------------------------------- helpers


def test_usage_defaults_to_zero_without_usage():
    assert _usage(_Resp(usage=False)) == (0, 0)
    assert _usage(object()) == (0, 0)


def test_apply_params_noop_on_empty():
    kwargs = {"model": "m"}
    _apply_params(kwargs, None)
    assert kwargs == {"model": "m"}


def test_drop_offending_param_matches_only_named_fields():
    kwargs = {"temperature": 0.4, "extra_body": {"custom": 1}}
    assert _drop_offending_param(kwargs, "something about seed") is False
    assert _drop_offending_param(kwargs, "custom is not permitted") is True
    assert "extra_body" not in kwargs
