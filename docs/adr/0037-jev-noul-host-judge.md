# ADR 0037 — Host-side Jev Noul-only judge under `judge:`

Status: Proposed

## Context

Prose gates are the language's reliability mechanism (ADR 0004). The host
turns a `gates:` relation into one transition by SPEC §5 first-true: scan
eligible gates in author order and fire the first that evaluates true.
Consecutive prose-only gates are fused into one `LLM.judge` call (ADR 0006);
the judge must not pick a "best" option out of order.

TypeSafe Jev (System One) can answer a batch of Noul questions cheaply. A
prior measurement compared two host mappings of that API onto mklang's judge:

- **Choice as `judge:` mapping** failed first-true. On the
  `priority_shadow` boundary machine (near-overlapping conditions; gold is
  the earlier, narrower gate — `docs/experiments/gate-divergence.md`) it
  scored 0/4; overall Choice accuracy was 0.818. Jev Choice is a multi-option
  pick, not an ordered first-true walk.
- **Noul-batch**, with the **host** applying first-probability-≥-threshold
  in gate order, preserved first-true (accuracy 1.0, n=11).

The existing host surface for "who judges" is the opt-in runtime `judge:`
key (ADR 0001, SPEC §2.1): a **global** override that forces one judge for
all prose gates. `.mkl` documents stay provider-neutral (ADR 0003). Exact
checks (amounts, dates, allowlists) already belong on `hook:` (ADR 0006),
not on an LLM.

Without a locked host mapping, a later adapter can silently choose Choice
as `judge:` mapping, wrap Jev as `hook:`, or treat Jev as a produce tier —
any of which would break first-true, mix probabilistic judgement into the
deterministic hook layer, or pin a vendor into generation.

Jev has no mklang-style untrusted fencing of its own. The same measurement
saw Choice injection accuracy of 0.833. ADR 0025 already requires judge
prompts to present produce output, reasoning, and context as delimited data
(`<data-NONCE>` fences plus an instruction that fenced spans are evidence,
not directives) while authored `when` conditions stay bare. A Jev judge
must keep that spirit on the System One `content` channel.

This ADR is **Phase 1 only**: it records the host mapping. It does not
implement an adapter, change the language, cut over production, or reopen
Choice as `judge:` mapping.

## Decision

Adopt a **Noul-only host judge** behind the existing **`judge:`** config
key. Reject Choice as `judge:` mapping. Reject wrapping Jev as `hook:`.
Jev is not a produce tier.

A later implementation may land only after a dedicated EXPLORE / Path B
measurement clears the quantitative bar named below. Until then the
decision is Proposed.

### Host mapping

| Rule | Spec |
|------|------|
| Unit of work | One gate decision → **one** `POST …/v1/systemone` call, model `jev-latest` (or a pinned successor). |
| Questions | One **Noul** per prose gate condition, in **mklang gate order**. Optional final Noul “none holds”, *or* a host default when no Noul fires. |
| Selection | The host walks results in order and fires the **first** condition whose probability is **≥ threshold**. That preserves first-true. Jev never picks a “best” option. |
| None path | If no Noul is ≥ threshold: take the explicit none Noul if present, else the host “none / continue” default (document per machine). |
| Config surface | Provider behind the existing **`judge:`** key. Per-tier judge is **out of this ADR** (a later host change). |
| Forbidden | Choice as `judge:` mapping; calling Jev from **`hook:`**; treating Jev as a produce tier. |
| Exact rules | Amounts, dates, allowlists stay on **`hook:`** (code), never Jev. |

Normative intent of the walk:

```
fence(state_text) → payload
noul_i = gate_condition_i for i in order
response = systemone(content=payload, questions=nouls)
for i in order:
  if response.noul[i].p >= threshold: return fire(gate_i)
return none_path()
```

### Host fence (ADR 0025 spirit)

| Rule | Spec |
|------|------|
| Why | Jev does not fence untrusted text the way the reference judge does. Path B requires injection accuracy ≥ **0.95** under Noul **after** the fence. |
| What is untrusted | Produce text, user / `state` fields, and any append not authored as gate prose. |
| Host duty | Before building the System One `content`, wrap untrusted spans with a **host fence**: clear delimiters plus an instruction that fenced text is data, not instructions — the same spirit as ADR 0025 sentinel fences and the judge-role paragraph. |
| Gate prose | Trusted; sent as Noul question text, **not** inside the untrusted fence. |
| Residual | If the fence cannot reach 0.95 injection accuracy: do not accept a production cutover; document the residual and stop. |
| Keys | API keys live only in the host env / secret store (ADR 0023) — never in a `.mkl` or in git. |

### Threshold

| Rule | Spec |
|------|------|
| Default | **`threshold = 0.5`** (the Noul-batch “first ≥ 0.5” rule from the prior measurement). |
| Tunable | Config on the Jev judge adapter only. Changing it requires evidence on a pinned gate-divergence corpus. |
| Hard gate | On a reopen spike, **`priority_shadow` accuracy must be 1.0** at the chosen threshold. |
| Confidence | Separate from threshold. Low confidence → prefer `escalate` / a divergence flag; **never** override first-true order. |
| Anti-pattern | Lowering the threshold to “fix” misses from Choice as `judge:` mapping, or using `max(Noul)` instead of first-≥. |

### Observability

Log every judge call as structured fields comparable to
`scripts/gate_divergence.py`:

| Field | Notes |
|-------|-------|
| `judge_provider` | e.g. `jev` / `jev-latest` |
| `mapping` | always `noul_first_ge` |
| `threshold` | value used |
| `noul_probs[]` | ordered |
| `chosen_index` / `none` | result |
| `confidence[]` or aggregate | if the API returns it |
| `latency_ms` | wall |
| `tokens_in` / estimated cost | claim-check, not marketing |
| `fence_applied` | bool |
| `corpus_id` / produce hash | when in harness |

Harness: reuse the `scripts/gate_divergence.py` entry-state corpus. A
live DeepSeek / OpenAI comparison (Path C) is recommended before calling
any later adapter production-ready, and only after keys plus an explicit
go-ahead.

### Out of scope (this ADR)

- Implementing the Jev judge adapter, wiring `POST …/v1/systemone`, or
  changing runtime config schema beyond recording the intended surface.
- Any SPEC / language / schema / conformance change. `.mkl` stays
  provider-neutral; `judge:` remains a host key.
- Production cutover of the reference judge onto Jev.
- Reopening Choice as `judge:` mapping (Path A is stopped).
- Per-tier judge (still a later host change).
- Wrapping Jev as `hook:`.

## Consequences

- **Positive.** First-true stays a host walk, not a model pick. Noul
  probabilities stay calibrated and ordered. `.mkl` documents remain
  provider-neutral via `judge:`. Cost and latency are a potential win
  *if* a later measurement shows one.
- **Negative.** The host owns fencing and the first-≥ walk. Global
  `judge:` still cannot scope to `fast` alone. The adapter is a vendor
  dependency. Path B (and ideally Path C) must pass before any
  production cutover.
- **Neutral / deferred.** Language change, platform deploy, Choice
  reopen, and a per-tier judge ADR.
- **Acceptance before code.** (1) Explicit EXPLORE go-ahead. (2) Path B
  quantitative bar green, including `priority_shadow` accuracy 1.0 and
  injection accuracy ≥ 0.95 after the fence. (3) This ADR accepted as
  the host mapping. (4) Path C recommended before production-ready.
  Phase 1 records the decision only.
