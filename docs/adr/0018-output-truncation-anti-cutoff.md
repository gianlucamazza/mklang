# ADR 0018 — Output truncation detection and host recovery policies

Status: Accepted (detect + report/halt + surfaces; continue deferred)

## Context

When a provider stops for length / max tokens, partial text was deposited as if
complete. Gates and `parse: list` saw silently cut-off content.

## Decision

1. **Detect always.** `Produced.truncated` + `finish_reason` (provider-normalized).
2. **Trace always.** Step records `truncated: true` (+ `finish_reason` when known).
   Fan-out parent steps get the same when any branch truncated.
3. **Live events.** `state-done` events carry `truncated` / `finish_reason`.
4. **Recovery host policy, default `report`:**
   - `report` — annotate and continue.
   - `halt` — `state-error: output-truncated`.
   - `continue` — **deferred** (stitch N pieces under cost budget; never default).
5. **Surfaces.** `engine.run(..., on_truncate=…)`, CLI `--on-truncate`, MCP
   `on_truncate`, console `ConsoleTools.on_truncate`, scripttest
   `run: { on_truncate: halt }`.
6. **`parse: list`.** Truncated produce → `state-error: parse-list-truncated`
   (clearer than a generic JSON parse failure). Under `halt`,
   `output-truncated` wins first.

## Checklist

| Item | Status |
|---|---|
| Detect + trace + events | **done** |
| `report` / `halt` policies | **done** |
| CLI / MCP / console / scripttest parity | **done** |
| Unit tests (mock produce) | **done** |
| Adapter unit tests with fake responses | **done** (Anthropic + OpenAI-compat) |
| `continue` stitching | deferred |

## Consequences

- Observability improves with zero `.mkl` changes.
- Auto-continue stays out so token budgets and traces stay honest.
