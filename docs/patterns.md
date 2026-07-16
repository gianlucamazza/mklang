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
- **Gate judging follows the state's tier by default** (SPEC §2.1): a `reasoning`
  state's high-stakes gates (refund thresholds, legal matters, human escalation) are
  judged by the reasoning model, not silently downgraded. The `judge:` config key is
  an **opt-in global override** that forces one model for *all* gate judging — a
  cost/latency optimization that also downgrades your most critical gates, so reach
  for it only when your gates really are uniform, cheap classifications.
- **Speculative cascade** beats a flat `reasoning` machine on cost: draft at `fast`,
  and let an `escalate` gate promote only the low-confidence cases to a `reasoning`
  state. Same answers, a fraction of the tokens.

## Reliability — gates are the safety net

- **Use code-hook gates for exact checks** (`hook: name` → host `(ctx, output) -> bool`).
  Amounts, equality, allowlists: do **not** ask the LLM. Put hooks **above** prose
  gates; keep `when` as the trace label. See `examples/hook_gates.mk` and ADR 0006.
  Custom tools/hooks: package entry points `mklang.tools` / `mklang.hooks` (see
  CONTRIBUTING).
- **Never put real I/O in generative states.** Searching, sending mail, charging a
  card: use `tool:` states (host callables). Do not write `execution: use tool X`
  on a generative state — the model cannot call tools there and will invent
  observations. Do not ask the model to "confirm the message was sent."
- **Treat `{{context}}` as untrusted** when it may contain customer or web text.
  Prose gates and prompts interpolate raw values; injection can steer transitions
  (SPEC §11). Prefer hooks + HITL before irreversible tools.
- **End every non-terminal state with an `otherwise` gate.** Without it, a run can
  `halt` with `no-gate-matched` — and if the judge returns garbage, the runtime
  **hard-halts** with `judge-unparseable` unless `otherwise` is eligible (soft
  fallback is recorded as `judge_fallback` in the trace). `mklang check` warns when
  the catch-all is missing.
- **Guarantee a reachable `END`.** `mklang check` errors if none exists.
- **Fix `unresolved-interpolation` lint before shipping.** `mklang lint` flags any
  `{{path}}` whose first segment no `context:` key, state `output:`, or (inside a
  fan-out) `item`/`index` provides — a typo (`{{kb_answr}}`) otherwise renders to an
  empty string and silently degrades the prompt. Under `--strict` it fails the run.
  If a host injects extra context keys at run time, declare them in `context:` with
  placeholder values so the reference to them resolves and the lint stays quiet.
  (When the root is an **inline `context:` map** — `ticket: {body: …}` — the second
  segment is checked too, so `{{ticket.bod}}` is caught. Deeper tails, and roots
  whose shape isn't statically known (state outputs, runtime `human`/`item`/`index`),
  are not verified against prose `structure`.)
- **Cap `repair`.** A `repair: N` with a modest `N` (1–2) plus a following
  `escalate`/`fail` gate prevents an endless self-correction loop.
- **Give escalation a safe sink.** Route hard cases to a terminal `human_review`
  state rather than failing — it's a graceful degrade, not a crash. With
  `--checkpoint --hitl` the run actually **pauses** on a fired escalate and
  `mklang resume --set human.reply="…"` feeds the decision to the handler
  (ADR 0008).
- **Size `budget` to the worst case.** Roughly: longest path × loop iterations, plus
  the width of any fan-out (a `sample: N` costs N steps). Leave headroom; hitting the
  budget is a `halt`.
- **Let `mklang check`/`lint` catch impossible budgets.** If `budget` is below the
  shortest path (in states) from `entry` to a gate `to: END`, validation reports
  error `budget-infeasible` — a guaranteed `budget-exhausted` before the first
  provider call. `budget < shortest + 2` is a warning (no headroom for a single
  repair). Fan-out states count as **1** in this static check (branch width is
  data-dependent), so a machine can still exhaust budget on a wide map even after
  the check passes (SPEC §7).
- **Map-reduce: size `budget` against data cardinality.** A fan-out charges
  `max(1, len(branches))` steps (SPEC §7), so `budget` is also a volume cap — an
  `over` on 30 items with `budget: 25` halts `budget-exhausted` before the reducer.
  Set `budget ≥ expected branches + machine overhead`, or bound the list before the
  fan-out. If the item count is unknown at authoring time, size for the worst case.
- **Use `--max-tokens` (cost budget) on long `call` trees.** The remaining budget is
  shared with sub-machines so a runaway child cannot burn tokens unbounded.
- **Fan-out concurrency** is a `ThreadPoolExecutor` with `max_workers=5` today —
  fine for modest `sample`/`over` widths; very wide maps should stay small or wait
  for the async roadmap item.

## Testing — pin the gates before you spend a token

- **Write scenario tests for every gate you would be embarrassed to see misfire.**
  `mklang test machine.mk --script machine.test.yaml` runs the machine against a
  **scripted LLM** (produce texts + judge picks) and scripted tools/hooks — no
  provider, no API key, fully deterministic. Each scenario is a named case in the
  conformance format (`llm`/`tools`/`hooks`/`run` + `expect`), and the runner
  shares its matcher with the [conformance suite](../conformance/README.md), so a
  green scenario means the *interpreter* would route your machine exactly that way.
- **Cover both the happy path and the escape hatches.** The value is in the
  branches you hope never fire: the escalate-to-human path, the repair loop giving
  up, the empty-tool-result fallback. Script the judge pick that steers into each
  and assert the `trace` skeleton (`state` → `to`, `policy`) lands where you think.
  See [`examples/triage.test.yaml`](../examples/triage.test.yaml) (happy path +
  KB-empty escalation).
- **Keep scenarios next to the machine** (`triage.mk` → `triage.test.yaml`) and
  run them in CI — a `.mk` edit that reroutes a gate fails the scenario, not a
  customer.

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
  model that honors it (most chat models do — some reasoner models ignore it). Each
  sample branch also sees its own `{{index}}` (0-based), so you can drive diversity
  explicitly — "you are branch {{index}}, take a different approach" (Tree-of-Thought,
  debate), not temperature alone.
- **`reason: true`** yields a captured chain only on models that expose thinking
  (Anthropic adaptive, DeepSeek `deepseek-reasoner`, o-series). On plain models the
  model still reasons internally; the trace just won't hold the scratchpad.
- **Per-tier `params` are applied** to each generation: `effort`/`thinking` on
  Anthropic, `reasoning_effort` on OpenAI/xAI, etc. They're best-effort — a param a
  provider doesn't support is dropped and the call retried, so mixing providers never
  breaks. Put them under `providers.<name>.params.<tier>` in the runtime config.
