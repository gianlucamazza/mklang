"""OpenAI-compat adapter: connection-error retry classification — no network."""

import pytest

from mklang.errors import ProviderError
from mklang.llm.base import is_connection_error
from mklang.llm.openai_compat import OpenAICompatLLM


class _Msg:
    content = "ok"
    reasoning_content = None


class _Choice:
    message = _Msg()
    finish_reason = "stop"


class _Usage:
    prompt_tokens = 1
    completion_tokens = 2


class _Resp:
    choices = [_Choice()]
    usage = _Usage()


class _Completions:
    def __init__(self, side_effect=None):
        self.calls = 0
        self._side_effect = side_effect

    def create(self, **kwargs):
        self.calls += 1
        if self._side_effect is not None:
            return self._side_effect(self.calls, kwargs)
        return _Resp()


def _adapter(side_effect=None, max_retries=3) -> OpenAICompatLLM:
    llm = OpenAICompatLLM.__new__(OpenAICompatLLM)
    llm.max_retries = max_retries
    completions = _Completions(side_effect)
    llm.client = type("C", (), {"chat": type("Ch", (), {"completions": completions})()})()
    return llm


def test_retries_connection_error_then_succeeds(monkeypatch):
    """Network blips carry no status_code; they must retry like a 503."""

    class APIConnectionError(Exception):
        pass

    def flaky(call, kwargs):
        if call < 3:
            raise APIConnectionError("Connection error.")
        return _Resp()

    monkeypatch.setattr("mklang.llm.openai_compat.time.sleep", lambda *_: None)
    llm = _adapter(side_effect=flaky)
    p = llm.produce("m", "sys", "user")
    assert p.text == "ok"
    assert llm.client.chat.completions.calls == 3


def test_connection_error_exhausts_retries_to_provider_error(monkeypatch):
    class APIConnectionError(Exception):
        pass

    def down(call, kwargs):
        raise APIConnectionError("Connection error.")

    monkeypatch.setattr("mklang.llm.openai_compat.time.sleep", lambda *_: None)
    llm = _adapter(side_effect=down)
    with pytest.raises(ProviderError, match="Connection error"):
        llm.produce("m", "sys", "user")
    assert llm.client.chat.completions.calls == 4  # initial call + max_retries


def test_is_connection_error_matches_by_name_and_subclass():
    class APIConnectionError(Exception):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    assert is_connection_error(APIConnectionError("down"))
    assert is_connection_error(APITimeoutError("slow"))
    assert not is_connection_error(ValueError("unrelated"))
