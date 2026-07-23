"""OpenAI-compatible adapter: DeepSeek, OpenAI, OpenRouter, xAI, Mistral, local."""

from __future__ import annotations

import time

from ..errors import JudgeUnparseable, ProviderError
from .base import (
    JUDGE_CONTEXT_CHARS,
    JUDGE_SYSTEM,
    Produced,
    TRANSIENT_STATUS,
    build_judge_user,
    is_connection_error,
    is_length_stop,
    parse_choice,
)
from .context_view import format_judge_context

# Params the OpenAI SDK accepts as top-level kwargs; everything else goes in extra_body.
_TOP_LEVEL_PARAMS = {"reasoning_effort", "max_tokens", "top_p", "seed"}


class OpenAICompatLLM:
    def __init__(self, api_key: str, base_url: str | None = None, max_retries: int = 3):
        from openai import OpenAI  # imported lazily so tests don't need the dep

        self.client = OpenAI(api_key=api_key or "unused", base_url=base_url)
        self.max_retries = max_retries

    def close(self) -> None:
        """Close the SDK client, interrupting any in-flight console request."""
        self.client.close()

    def _create(self, **kwargs):
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
                    time.sleep(0.5 * 2**attempt)
                    attempt += 1
                    continue
                dropped = _drop_offending_param(kwargs, msg)
                if dropped:
                    continue  # retry once without the rejected field
                raise ProviderError(str(e)) from e

    def produce(
        self,
        model: str,
        system: str,
        user: str,
        reason: bool = False,
        temperature: float = 0.4,
        params: dict | None = None,
    ) -> Produced:
        kwargs = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
        }
        _apply_params(kwargs, params)
        # Align with Anthropic's explicit budget: avoid provider-default short
        # completions that look like silent cutoff (ADR 0018). Tier params may
        # override; unsupported max_tokens is dropped and retried by _create.
        if "max_tokens" not in kwargs:
            kwargs["max_tokens"] = 4096
        r = self._create(**kwargs)
        choice = r.choices[0]
        msg = choice.message
        reasoning = getattr(msg, "reasoning_content", None) if reason else None
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
    ) -> tuple[int, str | None]:
        user = build_judge_user(
            conditions,
            output,
            format_judge_context(context, JUDGE_CONTEXT_CHARS),
            reasoning=reasoning,
        )
        r = self._create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},  # dropped-and-retried if unsupported
            temperature=0,
        )
        text = r.choices[0].message.content or ""
        idx, method = parse_choice(text, len(conditions))
        if idx is None:
            raise JudgeUnparseable(text[:200] or "(empty)")
        return idx, method


# Back-compat alias for tests that imported the private helper.
_parse_choice = parse_choice


def _usage(response: object) -> tuple[int, int]:
    u = getattr(response, "usage", None)
    if not u:
        return 0, 0
    return getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0


def _apply_params(kwargs: dict, params: dict | None) -> None:
    """Split per-tier params into SDK kwargs vs extra_body. Skip Anthropic-only keys."""
    if not params:
        return
    extra: dict = {}
    for key, value in params.items():
        if key == "thinking":  # Anthropic concept; not an OpenAI field
            continue
        if key in _TOP_LEVEL_PARAMS:
            kwargs[key] = value
        else:
            extra[key] = value
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
