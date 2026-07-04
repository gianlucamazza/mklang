"""Native Anthropic adapter. Optional: requires `pip install mklang[anthropic]`.

`reason: true` maps to adaptive thinking (per the current Claude API — no
budget_tokens on Opus 4.7+/Sonnet 5); the summarized thinking is captured as
`reasoning`."""

from __future__ import annotations

import json
import re

from ..errors import RefusalError
from .base import JUDGE_SYSTEM, Produced


class AnthropicLLM:
    def __init__(self, api_key: str, base_url: str | None = None):
        import anthropic  # lazy: only needed when this provider is active

        self.client = anthropic.Anthropic(api_key=api_key or None)

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
        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        # thinking: `reason` turns it on; config `thinking` can force adaptive/disabled.
        thinking = params.get("thinking")
        if thinking == "disabled":
            pass
        elif reason or thinking == "adaptive":
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
        if "effort" in params:  # low | medium | high | xhigh | max
            kwargs["output_config"] = {"effort": params["effort"]}
        msg = self.client.messages.create(**kwargs)
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

    def judge(self, model: str, conditions: list[str], output: str, context: dict) -> int:
        lines = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(conditions))
        user = (
            f"OUTPUT:\n{output}\n\nCONTEXT:\n{json.dumps(context, ensure_ascii=False)[:4000]}"
            f"\n\nCONDITIONS (priority order):\n{lines}"
        )
        msg = self.client.messages.create(
            model=model,
            max_tokens=16,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        m = re.search(r"\d+", text)
        idx = int(m.group()) - 1 if m else len(conditions) - 1
        return max(0, min(idx, len(conditions) - 1))
