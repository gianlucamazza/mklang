# Case study pack — two harness machines

**Status:** historical write-up (issue
[#121](https://github.com/gianlucamazza/mklang/issues/121)). Not a product
claim. Not a System One integration as shipped. Docs honesty pass required
before any public cite.

Every figure below is **historical**, copied from an in-repo row or a labeled
Lab receipt, and is shown with its date and **n**. Small **n**. Do not
generalize. Fresh per-machine tokens, latency, cost, and a new provider matrix are
**pending M4 (paid run, not yet approved)**.

## Shared setup

These are **not** stdlib machines and not third-party demos. Both live in the
published gate-divergence harness
([`scripts/gate_divergence.py`](../../scripts/gate_divergence.py);
protocol [`../experiments/gate-divergence.md`](../experiments/gate-divergence.md)).

| Knob | What was used | What was not |
| --- | --- | --- |
| Host | Local interpreter + harness scripts | No named account, no host address |
| Default judge | Omit `judge:` — SPEC §2.1 tier-following. Both machines are `default_tier: fast` | Not a pinned vendor in the `.mkl` |
| Path B judge | Opt-in host `judge: jev-*` (Noul-only first-true walk). Produce was **not** re-run; entry-state text is pinned | Not the default. Not a shipped System One product path. ADR 0037 stays **Proposed** |
| Corpus slice | Entry state only: `priority_shadow` / `none_holds` from `MACHINES` | No live produce, no external corpus |
| Fence | Interpreter ADR 0025 on the default-judge path (in package since 0.14.0, 2026-07-23; [`CHANGELOG.md`](../../CHANGELOG.md) L858). Path B applies an ADR 0025-spirit host fence around untrusted produce text | Gate-divergence **rows do not record** `fence_applied` |

Adapter posture stays `production_ready: false`
([`README.md`](../../README.md) Status, [#135](https://github.com/gianlucamazza/mklang/pull/135);
[`scripts/jev_noul_eval.py`](../../scripts/jev_noul_eval.py) `_verdict`).

## 1. `priority_shadow` — wrong-gate (first-true vs later narrower)

**Fail mode.** Both prose conditions hold. Gold is the **earlier, broader**
gate (`draft>broad`, SPEC §5 first-true). The later, narrower condition is
also true. A best-match / unordered pick can fire `narrow` — the wrong gate.

Pinned entry text (harness, not a live produce):
`REFUND 2000 EUR APPROVED FOR ORDER 71`
([`scripts/jev_noul_eval.py`](../../scripts/jev_noul_eval.py) `PINNED_OUTPUT`).

### Historical metrics

| What | Historical value | Date | n | Source |
| --- | --- | --- | --- | --- |
| Suite agreement, this machine included | **1.0** per machine (pooled **1.0**); accuracy **1.0** on gold-carrying machines | 2026-08-09 | DeepSeek + OpenAI ×3 each; 72/72 suite runs `done`; 66 scored for accuracy; **18** paraphrase pairs on this machine | [`gate-divergence.md`](../experiments/gate-divergence.md) Results row @ `3983472` |
| Path B first-true on this machine | **1.0** (one pinned entry-state item; suite n=6 machines) | 2026-10-05 | n=1 item (derived: one base doc per machine, `--paraphrase` off — [`scripts/jev_noul_eval.py`](../../scripts/jev_noul_eval.py) `run_eval` L188–208, L270; 6 machines = `CORE_MACHINES` L60–69); suite n=6 machines | Lab receipt on [issue #123](https://github.com/gianlucamazza/mklang/issues/123#issuecomment-5999319763); measured on PR #125 branch tip `8773760f` (2026-10-05) before merge `00e88c73` |
| Tokens / latency / USD | Per machine: **pending M4 (paid run, not yet approved)**. Path B suite-level only: latency median **~192 ms** (opt-in `jev-*` host judge; not per machine; not the default-judge path) | 2026-10-05 | suite n=6 machines (calls per median not stated) | [issue #123 receipt](https://github.com/gianlucamazza/mklang/issues/123#issuecomment-5999319763); no in-repo tokens or USD |

**Small-n.** Two providers, three repeats, one calendar day on the
boundary-corpus row. Path B scores one pinned entry-state item per
machine, no repeats — `priority_shadow` is n=1 inside a six-machine suite
(derived from `run_eval`, [`scripts/jev_noul_eval.py`](../../scripts/jev_noul_eval.py)
L188–208; the receipt states only suite n=6 and injection n=6).
The 2026-07-24 suite (four machines, this one **not yet in the corpus**)
already showed a same-provider dip (`severity_escalate` **0.667**,
DeepSeek + OpenAI ×3 each) — dated rows move.

## 2. `none_holds` — none-escape (totality)

**Fail mode.** No listed condition holds. Gold is the catch-all
(`classify>other`). The judge reaches it only by declining every prose
`when` (SPEC §5 totality / _none of the above_). A forced pick is a
none-escape miss.

Pinned entry text: `MAINTENANCE WINDOW SCHEDULED FOR SUNDAY`
([`scripts/jev_noul_eval.py`](../../scripts/jev_noul_eval.py) `PINNED_OUTPUT`).

### Historical metrics

| What | Historical value | Date | n | Source |
| --- | --- | --- | --- | --- |
| Suite agreement, this machine included | **1.0** per machine (pooled **1.0**); accuracy **1.0** on gold-carrying machines | 2026-08-09 | DeepSeek + OpenAI ×3 each; 72/72 suite runs; **18** paraphrase pairs on this machine | [`gate-divergence.md`](../experiments/gate-divergence.md) Results row @ `3983472` |
| Path B per-machine accuracy | not a separately named receipt row. The receipt's "Overall acc 1.0 (n=6 machines)" means each of the six scored 1.0 on its single pinned item (n=1; no repeats) — derived from `scripts/jev_noul_eval.py` L188–208, not stated in the receipt | 2026-10-05 | n=1 item (derived: `run_eval` L188–208, `--paraphrase` off L270; `CORE_MACHINES` L60–69); suite n=6 machines | Same [issue #123](https://github.com/gianlucamazza/mklang/issues/123#issuecomment-5999319763) receipt; still small-n — do not treat the suite line as extra repeats |
| Tokens / latency / USD | Per machine: **pending M4 (paid run, not yet approved)**. Path B suite-level only: latency median **~192 ms** (opt-in `jev-*` host judge; not per machine; not the default-judge path) | 2026-10-05 | suite n=6 machines (calls per median not stated) | [issue #123 receipt](https://github.com/gianlucamazza/mklang/issues/123#issuecomment-5999319763); no in-repo tokens or USD |

**Small-n.** Same two-provider, one-day boundary row as machine 1. No
dated gate-divergence row before 2026-08-09 (boundary corpus added
2026-07-28).

## Fence under untrusted append

Path B’s published fail mode is an untrusted append on produce text that
tries to rewrite gate order (later/narrower over first-true). The host
wraps that text in `<data-NONCE>` and treats the span as evidence, not
instructions ([`docs/guides/jev-noul-judge.md`](../guides/jev-noul-judge.md);
ADR 0025 spirit). Authored `when` prose stays outside the fence.

| What | Historical value | Date | n | Fence |
| --- | --- | --- | --- | --- |
| Fenced injection accuracy | **1.0** | 2026-10-05 | **n=6** | Applied (Lab receipt, [issue #123](https://github.com/gianlucamazza/mklang/issues/123#issuecomment-5999319763)) |
| Gate-divergence `fence_applied` | not recorded on the dated rows | 2026-08-09 | 72/72 runs | Interpreter ADR 0025 was already in 0.14.0 (2026-07-23); the row does not log the flag |
| Fresh injection / fence re-measure | **pending M4 (paid run, not yet approved)** | — | — | — |

## Not run

- **C3 Anthropic pass** ([#60](https://github.com/gianlucamazza/mklang/issues/60)):
  **not run**. On hold. Every dated gate-divergence row still lists Anthropic
  as skipped / keyless / billing-blocked. This pack does not close #60.
- **M4 Evidence Release** live dispatch: not approved here. Do not quote the
  2026-10 evidence directory as a provider result (skeleton + empty ledger).
- **Path C** (live DeepSeek / OpenAI vs the opt-in host judge): not in this
  pack’s sources.

## Source register

| Number | Historical label | Source (lines at `3983472`) | Commit / receipt | Date |
| --- | --- | --- | --- | --- |
| Agreement **1.0** (spam machine, 6 runs `done`) | historical; n=6 runs (3×2 providers) | [`docs/experiments/gate-divergence.md`](../experiments/gate-divergence.md) L151 | `3983472` (row first landed `817c18e`) | 2026-07-16 |
| Agreement **1.0** per machine (24/24, 15/15 pairs) | historical; n=24 runs | same file L152 | `3983472` (row first landed `633bf79`) | 2026-07-23 |
| Pooled **0.917**; `severity_escalate` **0.667** | historical; DeepSeek + OpenAI ×3 each (24/24 suite) | same file L153 | `3983472` (row first landed `397d5ef`) | 2026-07-24 |
| Agreement **1.0** per machine (24/24) | historical; n=24 runs | same file L154 | `3983472` (row first landed `79c7aab`) | 2026-07-27 |
| Agreement / accuracy / paraphrase **1.0**; 72/72; 66 scored; `priority_shadow` / `none_holds` **18** pairs each | historical; two providers, one day | same file L155 | `3983472169672da15173d21226c14705f1f7667b` | 2026-08-09 |
| Path B `priority_shadow` **1.0** (n=1 item); fenced injection **1.0** (**n=6**); suite n=6 machines; receipt verdict `path_b.verdict` HOLD (spike only), `choice_mapping` STOP | historical spike; small n | [issue #123 Lab receipt](https://github.com/gianlucamazza/mklang/issues/123#issuecomment-5999319763) (also linked from [`docs/what-mklang-is.md`](../what-mklang-is.md) L18); n=1 derived from [`scripts/jev_noul_eval.py`](../../scripts/jev_noul_eval.py) L188–208 | measured on PR #125 branch tip `8773760f` (2026-10-05) before merge `00e88c73` | 2026-10-05 |
| `production_ready: false` | current adapter posture | [`README.md`](../../README.md) L326; [`scripts/jev_noul_eval.py`](../../scripts/jev_noul_eval.py) L118 | `b1dbb50` / `#135`; script `00e88c73` | 2026-10-10 / 2026-10-05 |
