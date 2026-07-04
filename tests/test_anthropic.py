"""Anthropic adapter: params mapping, usage, and refusal — no network, no anthropic dep.

We bypass __init__ (which imports the optional `anthropic` package) and inject a fake
client, then assert the request kwargs the adapter builds."""

import pytest

from mklang.errors import RefusalError
from mklang.llm.anthropic import AnthropicLLM


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Usage:
    input_tokens, output_tokens = 3, 2


class _Msg:
    def __init__(self, stop_reason="end_turn"):
        self.content = [_Block("ok")]
        self.stop_reason = stop_reason
        self.usage = _Usage()


class _Messages:
    def __init__(self, stop_reason="end_turn"):
        self.captured = None
        self._stop = stop_reason

    def create(self, **kwargs):
        self.captured = kwargs
        return _Msg(self._stop)


class _Client:
    def __init__(self, stop_reason="end_turn"):
        self.messages = _Messages(stop_reason)


def _adapter(stop_reason="end_turn") -> AnthropicLLM:
    llm = AnthropicLLM.__new__(AnthropicLLM)  # skip __init__ / the anthropic import
    llm.client = _Client(stop_reason)
    return llm


def test_params_map_to_thinking_and_effort():
    llm = _adapter()
    p = llm.produce(
        "claude-x", "sys", "hi", reason=True, params={"thinking": "adaptive", "effort": "high"}
    )
    cap = llm.client.messages.captured
    assert cap["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert cap["output_config"] == {"effort": "high"}
    assert p.text == "ok" and p.input_tokens == 3 and p.output_tokens == 2


def test_thinking_disabled_suppresses_thinking():
    llm = _adapter()
    llm.produce("claude-x", "sys", "hi", reason=True, params={"thinking": "disabled"})
    assert "thinking" not in llm.client.messages.captured


def test_refusal_raises():
    llm = _adapter(stop_reason="refusal")
    with pytest.raises(RefusalError):
        llm.produce("claude-x", "sys", "hi")
