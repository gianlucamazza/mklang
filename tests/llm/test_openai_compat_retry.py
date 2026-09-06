"""OpenAI-compat adapter: connection-error retry classification — no network."""

import pytest

from mklang.errors import ProviderError
from mklang.llm.base import is_connection_error
from mklang.llm.openai_compat import OpenAICompatLLM, OpenAICompatProfile


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
    def __init__(self):
        self.choices = [_Choice()]
        self.usage = _Usage()


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
    llm.profile = OpenAICompatProfile()
    return llm


def test_close_delegates_to_sdk_client():
    llm = _adapter()
    closed = []
    llm.client.close = lambda: closed.append(True)
    llm.close()
    assert closed == [True]


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


def test_a_routing_constraint_is_never_dropped_to_make_a_call_succeed(monkeypatch):
    """A provider-routing block is a promise about where the customer's text goes.

    `_drop_offending_param` matches an `extra_body` key by substring against the
    lower-cased error message, and the key here is called `provider` — a word that
    appears in ordinary OpenRouter errors ("Provider returned error"). Dropping it and
    retrying *succeeds*, against whatever provider the router then picks: no `only`, no
    `zdr`, no `data_collection: deny`, fallbacks back on. The run reports success and
    the text went somewhere the configuration excluded.

    A run that fails is recoverable. A run that succeeded against the wrong vendor is
    not — so this must refuse, and say why.
    """

    class BadRequest(Exception):
        status_code = 400

    seen: list[dict] = []

    def rejects_once(call, kwargs):
        seen.append(dict(kwargs.get("extra_body") or {}))
        if call == 1:
            raise BadRequest("Provider returned error")
        return _Resp()

    routing = {"provider": {"only": ["azure"], "zdr": True, "data_collection": "deny"}}
    llm = _adapter(side_effect=rejects_once)
    with pytest.raises(ProviderError, match="routing"):
        llm.produce("m", "sys", "user", params=routing)
    assert all("provider" in body for body in seen), (
        "the routing constraint must never be retried away: " f"{seen}"
    )


def test_a_model_knob_is_still_negotiated_away_and_says_so():
    """The other half of the guard: refusing everything would be the opposite mistake.

    A provider that does not support a generation knob still answers the question, so
    that param is dropped and the call retried — but no longer in silence: the drop is
    an event, because «why did this run behave differently» has to be answerable.
    """
    events: list[dict] = []

    def rejects_once(call, kwargs):
        if call == 1:
            raise RuntimeError("unknown field: thinking")
        return _Resp()

    llm = _adapter(side_effect=rejects_once)
    llm.produce("m", "sys", "user", params={"thinking": {"type": "enabled"}},
                on_event=events.append)
    assert llm.client.chat.completions.calls == 2
    assert {"event": "param_dropped", "name": "thinking", "where": "extra_body"} in events
