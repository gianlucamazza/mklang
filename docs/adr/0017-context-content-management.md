# ADR 0017 — Context & content management: host budgets first, language zones later

Status: Accepted (Layer 0–1; Layer 2 language faces deferred)

## Context

The blackboard accumulates without bound. The judge CONTEXT blob was capped at
`JUDGE_CONTEXT_CHARS` with a silent prefix slice. Formal dual-channel zones
remain a non-goal for the current language line (SPEC §11).

## Decision

Stratify; implement bottom-up:

1. **Layer 0 — host rendering budgets.** Judge CONTEXT: head+tail with explicit
   `…[context_truncated]…` marker (never silent prefix-only). Produce-prompt
   char budgets and console history windowing are **not** claimed done yet.
2. **Layer 1 — machine patterns.** Explicit compress states / examples.
3. **Layer 2 — deferred language faces.** `context_policy`, pin, trusted zones.

## Checklist

| Item | Status |
|---|---|
| Judge CONTEXT head+tail marker | **done** (`llm/context_view.py`) |
| SPEC §5 wording | **done** |
| Produce-prompt char budget | **done** (`interpolate.PROMPT_VALUE_CHARS`, `run(prompt_value_chars=…)`) |
| Console history window | **done** (`history_for_brain`, prompt-only; full audit kept) |
| Compress pattern example | **done** (`examples/research_compress.mk` + scenario test) |
| `std_compress` / language faces | deferred |

## Consequences

- Existing `.mk` files keep working.
- Authors still own semantic summarization; the host only makes judge truncation visible.
