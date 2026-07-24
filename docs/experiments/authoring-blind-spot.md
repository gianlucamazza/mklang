# Authoring-loop blind_spot results

**Date:** 2026-07-23
**Provider / model:** deepseek / deepseek-reasoner (historical run; retired 2026-07-24)
**Repeats:** 3 · **Items:** 20
**Corpus:** `docs/experiments/authoring-corpus.yaml`
**Harness:** `scripts/authoring_blind_spot.py` (author → static check → scripted acceptance)

## Headline

| Metric | Value |
| --- | --- |
| check_pass_rate | **0.7167** |
| behaviour_pass_rate | **0.7** |
| **blind_spot** | **0.0167** |
| fraction needing ≥1 repair | 0.4167 |
| fraction exhausted repair without check_pass | 0.2833 |

**Verdict (B1):** static gate substantially sufficient — **do not build `test_machine`.**

Thresholds (fixed in advance, issue #59): `<0.10` close B1 / `0.10–0.25` opt-in `test_machine` / `>0.25` required step + 1.1.0 headline.

### Interpretation

- **blind_spot is tiny** (1 of 60 trials): when the static check passes, the
  hand-written acceptance almost always passes too. The structural premise
  “valid ≠ correct” remains true, but its measured magnitude under a
  contract-pinned authoring corpus does not justify a behavioural gate in the
  loop.
- **Most failures are check failures**, not silent behavioural wrongness.
  Hard shapes: `escalate_severity` 0/3, `tool_then_reply` 0/3 — the author
  never produced a statically valid machine within one repair. That is an
  **authoring reliability** problem (prompt / repair budget), not a blind_spot.
- **B2 rider:** 41.7% of trials needed a second author pass; 28.3% still failed
  check after that. The shared `budget: 16` comment on `agent.mkl` (“incl. an
  authoring repair”) is optimistic for multi-gate / multi-state requests; a
  dedicated repair budget remains an open product choice, orthogonal to
  `test_machine`.

## Per-item

| id | shape | check_pass | behaviour_pass | mean author attempts |
| --- | --- | --- | --- | --- |
| `accumulate_notes` | accumulate | 1/3 | 1/3 | 1.67 |
| `budget_tight` | linear | 3/3 | 3/3 | 1.0 |
| `call_child` | call | 3/3 | 3/3 | 1.33 |
| `default_tier_fast` | linear | 3/3 | 3/3 | 1.0 |
| `escalate_severity` | escalate | 0/3 | 0/3 | 2.0 |
| `fail_gate` | fail | 1/3 | 1/3 | 1.67 |
| `hitl_review` | escalate | 2/3 | 2/3 | 1.33 |
| `linear_echo` | linear | 2/3 | 2/3 | 1.33 |
| `linear_summarize` | linear | 2/3 | 2/3 | 1.67 |
| `multi_gate_otherwise_last` | routing | 3/3 | 3/3 | 1.33 |
| `parse_list` | parse_list | 3/3 | 3/3 | 1.33 |
| `reason_flag` | linear | 3/3 | 3/3 | 1.33 |
| `repair_grounding` | repair | 2/3 | 1/3 | 1.33 |
| `route_sentiment` | routing | 3/3 | 3/3 | 1.0 |
| `route_spam` | routing | 1/3 | 1/3 | 1.67 |
| `sample_fanout` | fanout | 3/3 | 3/3 | 1.33 |
| `tool_calc` | tool | 3/3 | 3/3 | 1.0 |
| `tool_search_stub` | tool | 3/3 | 3/3 | 1.33 |
| `tool_then_reply` | tool | 0/3 | 0/3 | 2.0 |
| `two_step_plan` | multi_state | 2/3 | 2/3 | 1.67 |

## Blind-spot trials (check ok, behaviour fail)

- `repair_grounding` r2: repair-then-ok: result: expected '30 days', got '365 days'; repair-then-ok: trace.length: expected 2, got "1 (['answer'])"

## Related

- Issue #59 · validation report 2026-07-23 (B1/B2)
- ADR 0028 (1.0 provisional posture — B1 no longer forces a 2.0)
