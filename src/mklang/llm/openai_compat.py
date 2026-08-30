"""Shared adapter for providers that expose the OpenAI chat-completions protocol."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..errors import CancellationError, JudgeUnparseable, ProviderError
from .base import (
    JUDGE_CONTEXT_CHARS,
    JUDGE_SYSTEM,
    TRANSIENT_STATUS,
    LLMDelta,
    LLMEvent,
    Produced,
    build_judge_user,
    is_connection_error,
    is_length_stop,
    parse_choice,
)
from .context_view import format_judge_context

# Params the OpenAI SDK accepts as top-level kwargs; everything else goes in extra_body.
_TOP_LEVEL_PARAMS = {"reasoning_effort", "max_tokens", "max_completion_tokens", "top_p", "seed"}


@dataclass(frozen=True)
class OpenAICompatProfile:
    """Declared protocol policy for an OpenAI-compatible provider."""

    omit_temperature_when_thinking: bool = False
    supports_response_format: bool = True
    max_output_tokens_param: str = "max_tokens"
    supports_temperature: bool = True


class OpenAICompatLLM:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        max_retries: int = 3,
        *,
        profile: OpenAICompatProfile | None = None,
    ):
        from openai import OpenAI  # imported lazily so tests don't need the dep

        self.client = OpenAI(api_key=api_key or "unused", base_url=base_url)
        self.max_retries = max_retries
        self.profile = profile or OpenAICompatProfile()

    def close(self) -> None:
        """Close the SDK client, interrupting any in-flight console request."""
        self.client.close()

    def _create(self, *, on_event: LLMEvent | None = None, **kwargs):
        """Robust create: retry transient errors with backoff; drop any single param a
        provider rejects (unsupported temperature / reasoning_effort / extra_body key)."""
        attempt = 0
        while True:
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:  # classify, then retry or re-raise
                status = getattr(e, "status_code", None)
                msg = str(e).lower()
                transient = status in TRANSIENT_STATUS or is_connection_error(e)
                if transient and attempt < self.max_retries:
                    _notify(on_event, "retry", attempt=attempt + 1, status=status)
                    time.sleep(0.5 * 2**attempt)
                    attempt += 1
                    continue
                dropped = _drop_offending_param(kwargs, msg)
                if dropped:
                    continue  # retry once without the rejected field
                detail = str(e)
                model = kwargs.get("model")
                if model and ("model" in msg or "not found" in msg):
                    detail = (
                        f"{detail} (configured model={model!r}; verify the provider model catalog)"
                    )
                raise ProviderError(detail) from e

    def _stream_create(
        self, kwargs: dict, *, on_event: LLMEvent | None = None, on_delta: LLMDelta
    ):
        kwargs = dict(kwargs)
        attempt = 0
        while True:
            try:
                stream = self.client.chat.completions.create(
                    **kwargs, stream=True, stream_options={"include_usage": True}
                )
                text: list[str] = []
                reasoning: list[str] = []
                usage = None
                finish = None
                for chunk in stream:
                    usage = getattr(chunk, "usage", None) or usage
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    choice = choices[0]
                    finish = getattr(choice, "finish_reason", None) or finish
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        continue
                    content = getattr(delta, "content", None)
                    if content:
                        text.append(content)
                        on_delta(content, "content")
                    thought = getattr(delta, "reasoning_content", None) or getattr(
                        delta, "reasoning", None
                    )
                    if thought:
                        reasoning.append(thought)
                        on_delta(thought, "reasoning")
                return "".join(text), "".join(reasoning) or None, usage, finish
            except Exception as e:
                if isinstance(e, CancellationError):
                    raise
                status = getattr(e, "status_code", None)
                msg = str(e).lower()
                transient = status in TRANSIENT_STATUS or is_connection_error(e)
                if transient and attempt < self.max_retries:
                    _notify(on_event, "retry", attempt=attempt + 1, status=status)
                    time.sleep(0.5 * 2**attempt)
                    attempt += 1
                    continue
                if "stream_options" in msg:
                    kwargs.pop("stream_options", None)
                    continue
                raise ProviderError(str(e)) from e

    def produce(
        self,
        model: str,
        system: str,
        user: str,
        reason: bool = False,
        temperature: float = 0.4,
        params: dict | None = None,
        on_event: LLMEvent | None = None,
        on_delta: LLMDelta | None = None,
    ) -> Produced:
        kwargs = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
        }
        _apply_params(kwargs, params, self.profile)
        if not self.profile.supports_temperature:
            kwargs.pop("temperature", None)
        # Align with Anthropic's explicit budget: avoid provider-default short
        # completions that look like silent cutoff (ADR 0018). Tier params may
        # override; unsupported provider parameters are dropped and retried by
        # _create. OpenAI's current GPT models require max_completion_tokens.
        output_param = self.profile.max_output_tokens_param
        if output_param not in kwargs:
            kwargs[output_param] = 4096
        if on_delta is not None:
            text, stream_reasoning, usage, finish = self._stream_create(
                kwargs, on_event=on_event, on_delta=on_delta
            )
            it, ot = _usage_from(usage)
            return Produced(
                text=text.strip(),
                reasoning=stream_reasoning if reason else None,
                input_tokens=it,
                output_tokens=ot,
                truncated=is_length_stop(finish),
                finish_reason=finish,
            )
        r = self._create(on_event=on_event, **kwargs)
        choice = r.choices[0]
        msg = choice.message
        reasoning = _reasoning_text(msg) if reason else None
        it, ot = _usage(r)
        finish = getattr(choice, "finish_reason", None)
        return Produced(
            text=(msg.content or "").strip(),
            reasoning=reasoning,
            input_tokens=it,
            output_tokens=ot,
            truncated=is_length_stop(finish),
            finish_reason=finish,
        )

    def judge(
        self,
        model: str,
        conditions: list[str],
        output: str,
        context: dict,
        reasoning: str | None = None,
        allow_none: bool = False,
        on_event: LLMEvent | None = None,
    ) -> tuple[int, str | None]:
        user = build_judge_user(
            conditions,
            output,
            format_judge_context(context, JUDGE_CONTEXT_CHARS),
            reasoning=reasoning,
            allow_none=allow_none,
        )
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if self.profile.supports_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        if not self.profile.supports_temperature:
            kwargs.pop("temperature", None)
        r = self._create(on_event=on_event, **kwargs)
        text = r.choices[0].message.content or ""
        idx, method = parse_choice(text, len(conditions) + (1 if allow_none else 0))
        if idx is None:
            raise JudgeUnparseable(text[:200] or "(empty)")
        self.last_judge_usage = _usage(r)
        return idx, method


# Back-compat alias for tests that imported the private helper.
_parse_choice = parse_choice


def _reasoning_text(message: object) -> str | None:
    """Normalize the reasoning field variants used by OpenAI-compatible APIs."""
    return getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)


def _usage(response: object) -> tuple[int, int]:
    u = getattr(response, "usage", None)
    if not u:
        return 0, 0
    return getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0


def _usage_from(usage: object) -> tuple[int, int]:
    if not usage:
        return 0, 0
    return (
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )


def _notify(callback: LLMEvent | None, event: str, **fields: object) -> None:
    if callback is not None:
        callback({"event": event, **fields})


def _apply_params(
    kwargs: dict, params: dict | None, profile: OpenAICompatProfile | None = None
) -> None:
    """Split per-tier params into SDK kwargs and provider-specific extra_body."""
    if not params:
        return
    extra: dict = {}
    for key, value in params.items():
        if key == "max_tokens" and profile and profile.max_output_tokens_param != "max_tokens":
            kwargs[profile.max_output_tokens_param] = value
            continue
        if key in _TOP_LEVEL_PARAMS:
            kwargs[key] = value
        else:
            extra[key] = value
    thinking = extra.get("thinking")
    if (
        profile
        and profile.omit_temperature_when_thinking
        and isinstance(thinking, dict)
        and thinking.get("type") == "enabled"
    ):
        # The provider profile declares this policy; the shared adapter stays generic.
        kwargs.pop("temperature", None)
    if extra:
        kwargs["extra_body"] = extra


def _drop_offending_param(kwargs: dict, err_msg: str) -> bool:
    """Remove the first param the error names (top-level or extra_body). Return True if
    something was dropped so the caller can retry."""
    for name in ("temperature", "response_format", *_TOP_LEVEL_PARAMS):
        if name in kwargs and name in err_msg:
            kwargs.pop(name, None)
            return True
    extra = kwargs.get("extra_body") or {}
    for name in list(extra):
        if name.lower() in err_msg:
            extra.pop(name, None)
            if not extra:
                kwargs.pop("extra_body", None)
            return True
    return False
