"""OpenAI-compatible adapter: DeepSeek, OpenAI, OpenRouter, xAI, Mistral, local."""

from __future__ import annotations

import json
import re
import time

from .base import JUDGE_SYSTEM, Produced

# Params the OpenAI SDK accepts as top-level kwargs; everything else goes in extra_body.
_TOP_LEVEL_PARAMS = {"reasoning_effort", "max_tokens", "top_p", "seed"}
_TRANSIENT_STATUS = (408, 409, 429, 500, 502, 503, 504)


class OpenAICompatLLM:
    def __init__(self, api_key: str, base_url: str | None = None, max_retries: int = 3):
        from openai import OpenAI  # imported lazily so tests don't need the dep

        self.client = OpenAI(api_key=api_key or "unused", base_url=base_url)
        self.max_retries = max_retries

    def _create(self, **kwargs):
        """Robust create: retry transient errors with backoff; drop any single param a
        provider rejects (unsupported temperature / reasoning_effort / extra_body key)."""
        attempt = 0
        while True:
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:  # noqa: BLE001 — classify, then retry or re-raise
                status = getattr(e, "status_code", None)
                msg = str(e).lower()
                if status in _TRANSIENT_STATUS and attempt < self.max_retries:
                    time.sleep(0.5 * 2**attempt)
                    attempt += 1
                    continue
                dropped = _drop_offending_param(kwargs, msg)
                if dropped:
                    continue  # retry once without the rejected field
                raise

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
        r = self._create(**kwargs)
        msg = r.choices[0].message
        reasoning = getattr(msg, "reasoning_content", None) if reason else None
        return Produced(text=(msg.content or "").strip(), reasoning=reasoning)

    def judge(self, model: str, conditions: list[str], output: str, context: dict) -> int:
        lines = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(conditions))
        user = (
            f"OUTPUT:\n{output}\n\n"
            f"CONTEXT:\n{json.dumps(context, ensure_ascii=False)[:4000]}\n\n"
            f"CONDITIONS (priority order):\n{lines}"
        )
        r = self._create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        m = re.search(r"\d+", r.choices[0].message.content or "")
        idx = int(m.group()) - 1 if m else len(conditions) - 1
        return max(0, min(idx, len(conditions) - 1))


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
    for name in ("temperature", *_TOP_LEVEL_PARAMS):
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
