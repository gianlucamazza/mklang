# Recommended configurations & flows

Operating guidance for building good machines. The **cookbook** ([`SPEC.md §10`](../SPEC.md))
maps _architectures_ to constructs; this page is about configuring them _well_.

## Tiers — route by cost, escalate for quality

| Use `fast` for               | Use `balanced` for     | Use `reasoning` for                   |
| ---------------------------- | ---------------------- | ------------------------------------- |
| classify, route, extract     | most generative states | validation, synthesis, critical gates |
| high-volume fan-out branches | drafting               | final answers, policy judgements      |

- **Default `default_tier: balanced`.** Override per state; don't reach for
  `reasoning` reflexively — it's the expensive tier.
- **Set `judge` to a cheap/fast model** in the runtime config. Gate judging is a
  small classification; paying reasoning-tier prices for it is waste.
- **Speculative cascade** beats a flat `reasoning` machine on cost: draft at `fast`,
  and let an `escalate` gate promote only the low-confidence cases to a `reasoning`
  state. Same answers, a fraction of the tokens.

## Reliability — gates are the safety net

- **End every non-terminal state with an `otherwise` gate.** Without it, a run can
  `halt` with `no-gate-matched` — and if the judge returns garbage, the runtime
  **hard-halts** with `judge-unparseable` unless `otherwise` is eligible (soft
  fallback is recorded as `judge_fallback` in the trace). `mklang check` warns when
  the catch-all is missing.
- **Guarantee a reachable `END`.** `mklang check` errors if none exists.
- **Cap `repair`.** A `repair: N` with a modest `N` (1–2) plus a following
  `escalate`/`fail` gate prevents an endless self-correction loop.
- **Give escalation a safe sink.** Route hard cases to a terminal `human_review`
  state rather than failing — it's a graceful degrade, not a crash.
- **Size `budget` to the worst case.** Roughly: longest path × loop iterations, plus
  the width of any fan-out (a `sample: N` costs N steps). Leave headroom; hitting the
  budget is a `halt`.
- **Use `--max-tokens` (cost budget) on long `call` trees.** The remaining budget is
  shared with sub-machines so a runaway child cannot burn tokens unbounded.
- **Fan-out concurrency** is a `ThreadPoolExecutor` with `max_workers=5` today —
  fine for modest `sample`/`over` widths; very wide maps should stay small or wait
  for the async roadmap item.

## Reasoning & observability

- **Use `reason: true` on states whose _why_ matters** (diagnosis, judgement,
  synthesis). The chain-of-thought lands in the trace, not the context — you get
  auditability without polluting downstream prompts. On reasoner models it maps to
  native thinking for free.
- **Read the trace, not just the result.** Every transition records the gate that
  fired and (for fan-out/`call`) the nested detail. When a run goes wrong, the trace
  says exactly where and why.

## Composite flows (which pattern when)

| Situation                                        | Reach for                                            |
| ------------------------------------------------ | ---------------------------------------------------- |
| One high-stakes answer, want robustness          | **Self-consistency** (`sample` → vote)               |
| Many similar items (docs, tickets, rows)         | **Map-Reduce** (`over` → reducer)                    |
| Quality-critical prose                           | **Reflexion** (`repair` loop, or a critic)           |
| Distinct request types → distinct handling       | **Router-of-experts** (classify → `call`)            |
| Mostly-easy workload, occasional hard case       | **Speculative cascade** (fast → escalate)            |
| Open-ended tool-using task                       | **ReAct** (think → `tool` state → `accumulate` loop) |
| Explore several partial solutions, keep the best | **Tree-of-Thought** (`sample` → select → loop)       |

## Provider notes

- The `.mk` never names a model — only tiers. Pick models in
  [`config/runtime.example.yaml`](../config/runtime.example.yaml) (default
  `active: deepseek`); keys come from `.env` (`DEEPSEEK_API_KEY`, …). Switching
  provider is a one-line `active:` change or `mklang run --provider …`.
- **Diversity for `sample`** comes from temperature; keep the sampling state on a
  model that honors it (most chat models do — some reasoner models ignore it).
- **`reason: true`** yields a captured chain only on models that expose thinking
  (Anthropic adaptive, DeepSeek `deepseek-reasoner`, o-series). On plain models the
  model still reasons internally; the trace just won't hold the scratchpad.
- **Per-tier `params` are applied** to each generation: `effort`/`thinking` on
  Anthropic, `reasoning_effort` on OpenAI/xAI, etc. They're best-effort — a param a
  provider doesn't support is dropped and the call retried, so mixing providers never
  breaks. Put them under `providers.<name>.params.<tier>` in the runtime config.
