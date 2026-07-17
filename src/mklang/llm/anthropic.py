"""Native Anthropic adapter. Optional: requires `pip install mklang[anthropic]`.

`reason: true` maps to adaptive thinking (per the current Claude API — no
budget_tokens on Opus 4.7+/Sonnet 5); the summarized thinking is captured as
`reasoning`."""

from __future__ import annotations

import json
import time

from ..errors import JudgeUnparseable, ProviderError, RefusalError
from .base import JUDGE_CONTEXT_CHARS, JUDGE_SYSTEM, TRANSIENT_STATUS, Produced, parse_choice


class AnthropicLLM:
    def __init__(self, api_key: str, base_url: str | None = None, max_retries: int = 3):
        import anthropic  # lazy: only needed when this provider is active

        # base_url is accepted for API symmetry with other providers; the SDK
        # picks it up via env / client options when needed.
        kwargs: dict = {"api_key": api_key or None}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.max_retries = max_retries

    def _create(self, **kwargs):
        """messages.create with transient retry and param drop-on-reject."""
        attempt = 0
        while True:
            try:
                return self.client.messages.create(**kwargs)
            except RefusalError:
                raise
            except Exception as e:  # classify, then retry or wrap
                # Refusal may surface as an API payload rather than our type.
                if getattr(e, "stop_reason", None) == "refusal":
                    raise RefusalError("the model declined this request") from e
                status = getattr(e, "status_code", None)
                msg = str(e).lower()
                if status in TRANSIENT_STATUS and attempt < self.max_retries:
                    time.sleep(0.5 * 2**attempt)
                    attempt += 1
                    continue
                if _drop_offending_param(kwargs, msg):
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
    ) -> Produced:
        params = params or {}
        kwargs: dict = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        # thinking: `reason` turns it on; config `thinking` can force adaptive/disabled.
        thinking = params.get("thinking")
        thinking_on = False
        if thinking == "disabled":
            pass
        elif reason or thinking == "adaptive":
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
            thinking_on = True
        # Anthropic rejects temperature alongside thinking; apply only when off.
        if not thinking_on:
            kwargs["temperature"] = temperature
        if "effort" in params:  # low | medium | high | xhigh | max
            kwargs["output_config"] = {"effort": params["effort"]}
        msg = self._create(**kwargs)
        if getattr(msg, "stop_reason", None) == "refusal":
            raise RefusalError("the model declined this request")
        text, reasoning = "", None
        for block in msg.content:
            if block.type == "text":
                text += block.text
            elif block.type == "thinking":
                reasoning = getattr(block, "thinking", None) or reasoning
        u = getattr(msg, "usage", None)
        it = getattr(u, "input_tokens", 0) if u else 0
        ot = getattr(u, "output_tokens", 0) if u else 0
        return Produced(text=text.strip(), reasoning=reasoning, input_tokens=it, output_tokens=ot)

    def judge(
        self,
        model: str,
        conditions: list[str],
        output: str,
        context: dict,
        reasoning: str | None = None,
    ) -> tuple[int, str | None]:
        lines = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(conditions))
        parts = [f"OUTPUT:\n{output}"]
        if reasoning:
            parts.append(f"REASONING:\n{reasoning}")
        parts.append(f"CONTEXT:\n{json.dumps(context, ensure_ascii=False)[:JUDGE_CONTEXT_CHARS]}")
        parts.append(f"CONDITIONS (priority order, 1-based):\n{lines}")
        parts.append('Reply with ONLY a JSON object: {"choice": <number>}.')
        user = "\n\n".join(parts)
        msg = self._create(
            model=model,
            max_tokens=64,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user}],
            temperature=0,
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        idx, method = parse_choice(text, len(conditions))
        if idx is None:
            raise JudgeUnparseable(text[:200] or "(empty)")
        return idx, method


def _drop_offending_param(kwargs: dict, err_msg: str) -> bool:
    """Drop the first rejected top-level field so the caller can retry once."""
    for name in ("temperature", "thinking", "output_config", "max_tokens"):
        if name in kwargs and name in err_msg:
            kwargs.pop(name, None)
            return True
    return False
