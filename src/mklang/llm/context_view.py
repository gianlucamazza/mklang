"""Host-side context rendering budgets (ADR 0017 — Layer 0 partial).

Judge CONTEXT must not silently drop the middle of a blob. Truncation is
explicit (middle marker) so authors can see it. Produce-prompt char budgets
remain deferred (see ADR checklist); this module owns the judge path only.
"""

from __future__ import annotations

import json


def format_judge_context(context: dict, limit: int) -> str:
    """Serialize context for the judge CONTEXT section under a character budget.

    Prefers a complete JSON dump; if over budget, keeps a head and tail of the
    dump with an explicit middle marker so truncation is visible (SPEC §5, ADR 0017).
    """
    raw = json.dumps(context, ensure_ascii=False)
    if len(raw) <= limit:
        return raw
    marker = "…[context_truncated]…"
    if len(marker) >= limit:
        return marker[:limit]
    remain = limit - len(marker)
    head = remain // 2
    tail = remain - head
    return raw[:head] + marker + raw[-tail:]
