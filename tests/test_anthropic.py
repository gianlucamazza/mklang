"""Anthropic adapter: params, temperature, retry, ProviderError, judge — no network."""

import pytest

from mklang.errors import ProviderError, RefusalError
from mklang.llm.anthropic import AnthropicLLM


class _Block:
    def __init__(self, text, typ="text"):
        self.type, self.text = typ, text
        if typ == "thinking":
            self.thinking = text


class _Usage:
    input_tokens, output_tokens = 3, 2


class _Msg:
    def __init__(self, stop_reason="end_turn", text="ok"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason
        self.usage = _Usage()


class _Messages:
    def __init__(self, stop_reason="end_turn", side_effect=None, text="ok"):
        self.captured = None
        self.calls = 0
        self._stop = stop_reason
        self._side_effect = side_effect
        self._text = text

    def create(self, **kwargs):
        self.calls += 1
        self.captured = kwargs
        if self._side_effect is not None:
            effect = self._side_effect
            if callable(effect):
                return effect(self.calls, kwargs)
            if isinstance(effect, list):
                item = effect[self.calls - 1]
                if isinstance(item, Exception):
                    raise item
                return item
        return _Msg(self._stop, self._text)


class _Client:
    def __init__(self, stop_reason="end_turn", side_effect=None, text="ok"):
        self.messages = _Messages(stop_reason, side_effect=side_effect, text=text)


def _adapter(stop_reason="end_turn", side_effect=None, text="ok") -> AnthropicLLM:
    llm = AnthropicLLM.__new__(AnthropicLLM)  # skip __init__ / the anthropic import
    llm.client = _Client(stop_reason, side_effect=side_effect, text=text)
    llm.max_retries = 3
    return llm


def test_params_map_to_thinking_and_effort():
    llm = _adapter()
    p = llm.produce(
        "claude-x", "sys", "hi", reason=True, params={"thinking": "adaptive", "effort": "high"}
    )
    cap = llm.client.messages.captured
    assert cap["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert cap["output_config"] == {"effort": "high"}
    assert "temperature" not in cap  # incompatible with thinking
    assert p.text == "ok" and p.input_tokens == 3 and p.output_tokens == 2


def test_max_tokens_stop_sets_truncated():
    llm = _adapter(stop_reason="max_tokens", text="partial")
    p = llm.produce("claude-x", "sys", "hi")
    assert p.truncated is True
    assert p.finish_reason == "max_tokens"
    assert p.text == "partial"


def test_thinking_disabled_suppresses_thinking():
    llm = _adapter()
    llm.produce("claude-x", "sys", "hi", reason=True, params={"thinking": "disabled"})
    cap = llm.client.messages.captured
    assert "thinking" not in cap
    assert cap["temperature"] == 0.4


def test_temperature_applied_without_thinking():
    llm = _adapter()
    llm.produce("claude-x", "sys", "hi", reason=False, temperature=0.9)
    assert llm.client.messages.captured["temperature"] == 0.9


def test_refusal_raises():
    llm = _adapter(stop_reason="refusal")
    with pytest.raises(RefusalError):
        llm.produce("claude-x", "sys", "hi")


def test_provider_error_wraps_api_failure():
    class Boom(Exception):
        status_code = 400

    def fail(call, kwargs):
        raise Boom("invalid request")

    llm = _adapter(side_effect=fail)
    with pytest.raises(ProviderError, match="invalid request"):
        llm.produce("claude-x", "sys", "hi")


def test_retries_transient_then_succeeds(monkeypatch):
    class Transient(Exception):
        status_code = 429

    def flaky(call, kwargs):
        if call < 3:
            raise Transient("rate limited")
        return _Msg()

    monkeypatch.setattr("mklang.llm.anthropic.time.sleep", lambda *_: None)
    llm = _adapter(side_effect=flaky)
    p = llm.produce("claude-x", "sys", "hi")
    assert p.text == "ok"
    assert llm.client.messages.calls == 3


def test_judge_parses_json_choice():
    llm = _adapter(text='{"choice": 2}')
    idx, method = llm.judge("m", ["a", "b", "c"], "out", {})
    assert idx == 1 and method == "json"
    assert "JSON object" in llm.client.messages.captured["messages"][0]["content"]


def test_judge_includes_reasoning():
    llm = _adapter(text='{"choice": 1}')
    llm.judge("m", ["ok"], "out", {}, reasoning="because X")
    body = llm.client.messages.captured["messages"][0]["content"]
    assert "REASONING:\nbecause X" in body


def test_judge_unparseable_raises():
    from mklang.errors import JudgeUnparseable

    llm = _adapter(text="no number here")
    with pytest.raises(JudgeUnparseable):
        llm.judge("m", ["a", "b"], "out", {})


def test_judge_out_of_range_raises_not_clamped():
    """{"choice": 0} (0-based) must not silently fire condition 1."""
    from mklang.errors import JudgeUnparseable

    llm = _adapter(text='{"choice": 0}')
    with pytest.raises(JudgeUnparseable):
        llm.judge("m", ["a", "b", "c"], "out", {})


def test_judge_oversized_choice_raises_not_clamped():
    from mklang.errors import JudgeUnparseable

    llm = _adapter(text='{"choice": 9}')
    with pytest.raises(JudgeUnparseable):
        llm.judge("m", ["a", "b"], "out", {})
