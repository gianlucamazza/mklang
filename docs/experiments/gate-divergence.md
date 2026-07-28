# Experiment: cross-provider gate divergence

## Hypothesis

The same mklang machine and inputs can produce **different gate traces** across
LLM providers, even when every run completes successfully. Document portability
("change `active:` and re-run") is **syntactic**; semantic agreement of prose
gates is an empirical property of the judges, not a language invariant.

## Why it matters

mklang's reliability story is "gates contain non-determinism." Prose gates are
judged by the same class of model that produces state output. If DeepSeek and
Claude fire different gates on the same blackboard, then:

- "same machine, any provider" is true for the **document**, not for **behavior**;
- production authors need hooks/HITL on high-stakes transitions;
- the conformance suite (scripted LLM) correctly pins the **interpreter** but
  does not measure judge reliability.

This is also the smallest publishable measurement next to the interpreter work.

## Method

Script: [`scripts/gate_divergence.py`](../../scripts/gate_divergence.py).

1. A **suite** of small synthetic machines, each stressing a different gate
   shape (`--machines`, default the single `gate_divergence` for release-gate
   comparability, or `all`):
   - `gate_divergence` — multi-way `ok` routing on a spam/ham/unknown label;
   - `sentiment_borderline` — a deliberately mixed review, so the
     positive/negative/mixed gates are genuinely contestable;
   - `severity_escalate` — an `escalate` gate that decides whether a human is
     paged (control-flow-critical divergence, SPEC §11);
   - `grounding_repair` — a `repair` loop on "grounded in the given fact".

   Plus a **boundary corpus** (added 2026-07-28) where the answer is defensible
   but not obvious, so the measurement can actually fail:
   - `threshold_edge` — a **marginal condition**: the amount sits exactly on the
     limit and the gate says "strictly greater";
   - `priority_shadow` — **near-overlapping gates**: both conditions are true and
     the narrower one is second, so SPEC §5's first-true rule fixes the answer;
   - `none_holds` — the output satisfies **no** condition, so the catch-all is
     correct and can only be reached through the judge's *none of the above*
     verdict (SPEC §5 _Totality_).
2. For each selected machine and each provider in the runtime config with an
   API key, run it (`--repeats N` optional). With `--paraphrase`, also run each
   machine's **reworded variants** — same states, same targets, same prompts,
   different `when` text.
3. Record per-run **gate signature** (ordered `state|gate|gate_via|to`, not full
   free-text outputs), the **route** (`state>to`, wording-independent), and
   whether the route equals the machine's **gold** route where one exists.
4. Report pairwise `same_signature` and `signature_agreement_rate`, **computed
   within each machine and wording variant** (cross-machine signatures differ by
   construction; a reworded variant is a different input), plus a `per_machine`
   breakdown, the cross/intra-provider decomposition, accuracy, and paraphrase
   invariance. The release gate enforces `--min-agreement` per-machine so no
   single machine hides behind a high pooled average.

```bash
uv run python scripts/gate_divergence.py
uv run python scripts/gate_divergence.py --machines all --providers deepseek,openai --repeats 3 \
  --jsonl /tmp/gate-div.jsonl
# boundary corpus + wording sensitivity + the metrics that can fail:
uv run python scripts/gate_divergence.py --machines all --paraphrase \
  --providers deepseek,openai --repeats 3 \
  --min-cross-agreement 0.8 --min-intra-agreement 0.8 --min-accuracy 0.8
# force one judge tier across providers (comparable to pre-0.5.2 fast-judge runs):
uv run python scripts/gate_divergence.py --judge-tier fast
```

> **Judge model since 0.5.2.** Gate judging now follows each state's tier by
> default (SPEC §2.1); the demo machine is `fast`-tier throughout, so the default
> judge here is the `fast` model — but any results collected before 0.5.2 used the
> old `judge:`-forced model and are **not comparable** with tier-following runs.
> Each row now records `judge_model` per gate and the run's `judge_tier`; use
> `--judge-tier` to pin a single tier when comparing across the change.

## Metrics

| Metric                          | Definition                                                                   |
| ------------------------------- | ---------------------------------------------------------------------------- |
| `signature`                     | Compact routing trace (gates + via + destinations)                           |
| `route`                         | Path only (`state>to`) — comparable across wordings                          |
| `same_signature`                | Pairwise equality of signatures                                              |
| `signature_agreement_rate`      | Fraction of within-group pairs that agree — **pooled over both pair kinds**  |
| `cross_provider_agreement_rate` | Agreement over pairs of **different** providers (the portability claim)      |
| `intra_provider_agreement_rate` | Agreement over repeats of the **same** provider (self-consistency)           |
| `accuracy`                      | Fraction of runs taking the **gold** route, where a machine declares one     |
| `gate_blind_spot`               | `agreement − accuracy`: how much consensus overstates correctness            |
| `paraphrase_invariance_rate`    | Same provider, same evidence, reworded conditions → same route?              |
| `per_machine` / `paraphrase`    | The same metrics broken down per suite machine / per wording set             |
| `distinct_signatures`           | Set of observed routing patterns                                             |

### Why the headline number was not enough

Through 2026-07-27 the reported figure was a single pooled
`signature_agreement_rate`, and it read **1.0** on four machines. That is not
evidence of judge reliability; it is a measure with **no discriminating power**,
for three separable reasons — each now has its own metric:

1. **The tasks were easy.** Every machine had an obvious right answer, so
   agreement had nowhere to go but 1.0. The boundary corpus (`threshold_edge`,
   `priority_shadow`, `none_holds`) puts the decision where competent judges can
   legitimately differ.
2. **Agreement ≠ correctness.** Two providers can concur on the *wrong* route,
   and the pooled rate scores that as perfect. `accuracy` against the gold route
   is the missing half; `gate_blind_spot` is the gap between them — the
   gate-judging analogue of the authoring-loop
   [`blind_spot`](./authoring-blind-spot.md).
3. **The pool mixed two questions.** With `--repeats 3` the pairwise set
   contained same-provider pairs (does one model repeat itself?) alongside
   cross-provider pairs (do two models agree?). Repeats of one model at
   `temperature=0` agree far more easily, so pooling them **inflates** the
   portability number. The two rates are now reported separately;
   `signature_agreement_rate` is kept, unchanged in meaning, so the pinned
   release history stays comparable — it is just no longer the number to quote.

Paraphrase invariance answers a fourth question none of the above can: whether a
verdict tracks the evidence or the phrasing. It compares a single provider
against itself across reworded conditions, so a low rate is unambiguous — the
same model, the same output, a different route, because the author wrote the
condition differently.

Optional later: majority vote over `N` repeats; Cohen's κ on first-step gate;
temperature ablation.

## Limitations

- **The boundary corpus has no live rows yet.** `threshold_edge`,
  `priority_shadow`, `none_holds`, the cross/intra decomposition, accuracy and
  paraphrase invariance are implemented and covered offline (scripted judges,
  `tests/repo/test_gate_divergence_script.py`); no dated live run has produced
  numbers for them. Until one appears in **Results**, treat them as
  instrumentation, not findings — and do not cite the 1.0 history as if it
  covered them.
- Gold routes encode **author intent under SPEC §5**, not a universal truth.
  `priority_shadow`'s gold follows from the first-true rule; `threshold_edge`'s
  from "strictly greater"; `none_holds`' from the catch-all. A machine with no
  defensible answer (`sentiment_borderline`) has no gold entry on purpose —
  scoring taste as correctness would be worse than not scoring at all.
- Live and non-deterministic; results change with model versions and dates.
- Small synthetic task — not a support-triage benchmark.
- Conformance suite remains the contract for **engine** semantics; this experiment
  is **not** a substitute.
- Cost: one produce + one judge per successful provider (plus short terminal).

## Results

| Date       | Providers                  | Agreement rate      | Distinct signatures | Notes                                                                                                                                                                                                                                                                       |
| ---------- | -------------------------- | ------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-16 | deepseek, openai (×3 each) | **1.0**             | 1                   | Tier-following judges (post-0.5.2 default). Synthetic spam machine; all 6 runs `done`. Shared signature: `label\|spam→spam_path \|\| spam_path\|otherwise→END`. Anthropic skipped (account billing / credit limit, not a missing key).                                      |
| 2026-07-23 | deepseek, openai (×3 each) | **1.0** per machine | 1 per machine       | First full **four-machine suite** run (`--machines all`). 24/24 runs `done`, agreement 1.0 within every machine (15/15 pairs each), zero gate errors. Free-text outputs diverge on the contestable machines while routing stays identical. Anthropic still billing-blocked. |
| 2026-07-24 | deepseek, openai (×3 each) | **0.917** pooled; **1.0** on 3/4 machines | 1–2 per machine | **1.0.1 release day.** Full four-machine suite: 24/24 `done`, `gate_errors: []`. `gate_divergence` / `sentiment_borderline` / `grounding_repair` stay **1.0**; **`severity_escalate` drops to 0.667** (one DeepSeek run took `otherwise→auto` instead of page-human). Release-gate (single machine) still **1.0**. Anthropic **key absent** locally and in GitHub Actions secrets (not only billing). |
| 2026-07-27 | deepseek, openai (×3 each) | **1.0** per machine (pooled **1.0**) | 1 per machine | Full four-machine suite, 24/24 `done`, `gate_errors: []`. Live smokes green. **`severity_escalate` back to 1.0** but the shared signature is `otherwise→auto` (not page-human) — agreement holds on the non-escalate path; still evidence that control-flow is model-sensitive across calendar days. Anthropic still **no key** in project/user `.env` (demo keys present: DeepSeek, OpenAI, Tavily only). |

### 2026-07-16 detail

```bash
uv run python scripts/gate_divergence.py --providers deepseek,openai --repeats 3
```

- **runs_done:** 6 (3×deepseek + 3×openai)
- **signature_agreement_rate:** `1.0` (all pairwise comparisons agreed)
- **distinct_signatures:**
  - `label|the output is the word "spam"|llm|spam_path || spam_path|otherwise|otherwise|END`
- **Interpretation:** On this tiny synthetic task, DeepSeek and OpenAI agreed on
  routing under default tier-following judges. This is a single data point — not a
  portability guarantee. High-stakes prose gates still need hooks/HITL (SPEC §11).
- **Anthropic:** live smoke and divergence blocked by provider billing
  (`invalid_request_error` / purchase credits), not by missing `ANTHROPIC_API_KEY`
  or adapter bugs. Re-run when the account has credit.

### 2026-07-23 detail — full four-machine suite

```bash
uv run python scripts/gate_divergence.py --machines all --providers deepseek,openai --repeats 3
```

- **runs_done:** 24 (4 machines × 2 providers × 3 repeats), 0 skipped, 0 failed,
  `gate_errors: []`
- **Judges:** tier-following (SPEC §2.1 default) — historical `deepseek-chat` and
  `gpt-5.4-mini` (both machines are `fast`-tier throughout)
- **Per-machine agreement** (15/15 within-machine pairs each):

  | Machine                | Agreement | Distinct signatures | Shared signature (abbreviated)         |
  | ---------------------- | --------- | ------------------- | -------------------------------------- |
  | `gate_divergence`      | **1.0**   | 1                   | `label\|spam→spam_path → END`          |
  | `sentiment_borderline` | **1.0**   | 1                   | `assess\|clearly negative→neg → END`   |
  | `severity_escalate`    | **1.0**   | 1                   | `triage\|page a human→human → END`     |
  | `grounding_repair`     | **1.0**   | 1                   | `answer\|grounded, states 30 days→END` |

- **Free text diverges, routing doesn't:** on `sentiment_borderline` and
  `severity_escalate` every pair reports `same_outputs: false` (the produced
  prose differs across runs and providers) while `same_signature: true` — the
  gates absorb the output non-determinism, which is the language's reliability
  claim in miniature. On the two anchored machines (`gate_divergence`,
  `grounding_repair`) even the outputs coincide.
- **Interpretation:** four gate shapes (multi-way routing, borderline judgement,
  control-flow `escalate`, `repair` grounding), two providers, full agreement.
  Still synthetic and still two providers — not a portability guarantee, and
  high-stakes prose gates keep needing hooks/HITL (SPEC §11) — but the
  four-machine harness is now exercised live end to end.
- **Anthropic:** unchanged — billing-blocked, not a key/adapter problem.

### 2026-07-24 detail — 1.0.1 release day (full suite + release gate)

**Release gate** (workflow `release.yml` on `v1.0.1`, default single machine,
`--require-providers deepseek,openai --min-agreement 1.0`):

- **runs_done:** 6 (3×deepseek + 3×openai on `gate_divergence`); 15 skipped
  (anthropic/google/openrouter/xai/mistral — no keys in CI secrets); 0 failed.
- **signature_agreement_rate:** **1.0** (release published to PyPI).

**Full four-machine suite** (maintainer re-run the same day):

```bash
uv run python scripts/gate_divergence.py --machines all --providers deepseek,openai --repeats 3
```

- **runs_done:** 24, 0 skipped, 0 failed, `gate_errors: []`
- **Pooled signature_agreement_rate:** **0.917**
- **Per-machine:**

  | Machine                | Agreement | Distinct signatures | Note |
  | ---------------------- | --------- | ------------------- | ---- |
  | `gate_divergence`      | **1.0**   | 1                   | Release-gate machine — stable |
  | `sentiment_borderline` | **1.0**   | 1                   | Free-text still diverges (`same_outputs: false`) |
  | `grounding_repair`     | **1.0**   | 1                   | Anchored |
  | `severity_escalate`    | **0.667** | 2                   | One DeepSeek repeat chose `otherwise→auto` instead of page-human |

- **Interpretation:** the release gate (easy multi-way `ok` routing) remains at
  1.0. The control-flow-critical `escalate` machine is **genuinely contestable**
  across repeats of the same provider — evidence for SPEC §11 hooks/HITL on
  high-stakes transitions, not a packaging regression. Recorded so the 1.0.1
  story is not over-claimed from the single-machine gate alone.
- **Anthropic / optional providers:** no `ANTHROPIC_API_KEY` in the maintainer
  `.env` (empty placeholder) **nor** in GitHub Actions repository secrets
  (`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY` only). Closing the
  three-provider gap needs a live key + credit (issue #60).

### 2026-07-27 detail — full suite re-run (DeepSeek + OpenAI)

Live smokes (`MKLANG_LIVE=1` × deepseek, openai) green. Full suite:

```bash
# keys from project .env (DeepSeek, OpenAI, Tavily present; Anthropic absent)
uv run python scripts/gate_divergence.py --machines all \
  --providers deepseek,openai --repeats 3 \
  --summary-json /tmp/gate-div-summary.json
```

- **runs_done:** 24, 0 skipped, 0 failed, `gate_errors: []`
- **signature_agreement_rate:** **1.0** pooled and **1.0** per machine
- **Per-machine:**

  | Machine                | Agreement | Distinct signatures | Shared signature (abbreviated) |
  | ---------------------- | --------- | ------------------- | ------------------------------ |
  | `gate_divergence`      | **1.0**   | 1                   | `label\|spam→spam_path → END` |
  | `sentiment_borderline` | **1.0**   | 1                   | `assess\|clearly negative→neg → END` |
  | `grounding_repair`     | **1.0**   | 1                   | `answer\|grounded, states 30 days→END` |
  | `severity_escalate`    | **1.0**   | 1                   | `triage\|otherwise→auto → END` (not page-human) |

- **Interpretation:** agreement recovered to 1.0 on the escalate machine, but
  **both providers chose the non-escalate path** consistently. Combined with
  2026-07-24's 0.667 / page-human split, control-flow escalate remains the
  probe machine — floor **0.5** in release stays justified; do not raise it to
  1.0 from a single good day.
- **Anthropic:** still not runnable locally (no `ANTHROPIC_API_KEY` in project
  or `~/.config/mklang/.env`). Issue #60 remains open until a key + credit
  exist; #72 runbook documents the ops steps.

## Release-gate floor policy

This section freezes how release floors are chosen and how machines enter the
release gate. Implementation lives in
[`.github/workflows/release.yml`](https://github.com/gianlucamazza/mklang/blob/main/.github/workflows/release.yml)
(live matrix job). Tracking:
[#64](https://github.com/gianlucamazza/mklang/issues/64),
[#69](https://github.com/gianlucamazza/mklang/issues/69).

### Current floors (package 1.x)

| Machine | Role | Floor (`signature_agreement_rate`) | Evidence |
| ------- | ---- | ---------------------------------- | -------- |
| `gate_divergence` | Easy multi-way `ok` routing — **release anchor** | **1.0** | Stable 1.0 on DeepSeek×OpenAI (2026-07-16 … 2026-07-24) |
| `severity_escalate` | Control-flow `escalate` — **contestability probe** | **0.5** | Observed **0.667** on 2026-07-24; floor allows contestability without letting total chaos pass |

Default script floor for any machine without an override is the global
`--min-agreement` (release uses **1.0**). Per-machine overrides use
`--min-agreement-by-machine name=rate`.

### How floors are chosen

1. **Evidence first.** A floor needs at least one dated full-suite (or
   release-gate) row in this document with provider, repeats, and per-machine
   rates. No floor change from a single maintainer anecdote.
2. **Anchor vs probe.** Anchor machines (easy, high-stakes for “package is
   broken”) stay at **1.0**. Probe machines (deliberately contestable control
   flow) may use a lower floor so the release does not pretend prose judges
   are deterministic; the floor must still fail total chaos (random routing).
3. **Who may change.** Maintainer PR that (a) updates the table above, (b)
   updates `release.yml` comments + flags in the same commit, (c) links the
   evidence row. No silent CI-only edits.
4. **Provider expansion.** When a new provider joins `--require-providers`,
   re-run the current release set at ≥3 repeats before tightening floors.
   Optional providers (present in the provider list but not required) may be
   skipped when the key is absent — they do not lower the required pair’s floor.

### Promoting a machine into the release gate

A suite machine moves from **suite-only** (`--machines all` maintainer runs)
into **release.yml** only when all of the following hold:

1. **Stable enough:** ≥2 dated runs (different calendar days or releases) at
   the proposed floor on the required providers, with `gate_errors: []`.
2. **Distinct signal:** the machine stresses a gate shape not already covered
   by an existing release machine (routing / borderline / escalate / repair …).
3. **Cost budget:** release live matrix stays within the workflow timeout; if
   adding a machine requires cutting repeats below 3, do not promote.
4. **Documented floor:** a row in the floors table with rationale (anchor vs
   probe). Contestable machines must not be promoted at 1.0 without evidence
   they actually hold 1.0 across repeats.
5. **Not a substitute for hooks:** promotion measures judge agreement; it does
   **not** remove the SPEC §11 guidance that high-stakes transitions need
   hooks/HITL in production machines.

Demotion (remove from release, keep in suite) is allowed when a machine becomes
noise (always 1.0 and redundant) or chronically flaky without product value;
record the reason in the next results row.

### Suite-only machines (not in release.yml)

| Machine | Why suite-only today |
| ------- | -------------------- |
| `sentiment_borderline` | Contestable free-text; routing has been 1.0 but free-text diverges — useful measurement, redundant with anchor for release |
| `grounding_repair` | Anchored repair loop; stable 1.0 — candidate for promotion if release cost allows and we want repair coverage |
| `threshold_edge` | Boundary corpus, **no live evidence yet** — promotion needs ≥2 dated rows per the rules above |
| `priority_shadow` | Boundary corpus, no live evidence yet. If it turns out judges routinely pick the narrower second gate, that is a finding about the priority rule, not a floor to lower |
| `none_holds` | Boundary corpus, no live evidence yet. Measures the *none of the above* verdict (SPEC §5); before that existed the machine could not route correctly at all |

Boundary machines must not enter the release gate on a floor invented before the
first live row: an unmeasured floor is a guess with CI authority.

## Anthropic secret + credit runbook

Closes the *ops* side of [#60](https://github.com/gianlucamazza/mklang/issues/60)
and [#72](https://github.com/gianlucamazza/mklang/issues/72). The adapter and
harness already support Anthropic; the gap is **account credit** and **keys in
the places that run live jobs**.

### Prerequisites

1. **Billing / credits** on the Anthropic account (past failures were
   `invalid_request_error` / purchase-credits — **not** a missing adapter).
2. **API key** with access to the models mapped in `config/runtime.yaml`
   (or project `config/runtime.yaml`) under `providers.anthropic.tiers`.

### Local

```bash
# .env (gitignored) — never commit
ANTHROPIC_API_KEY=sk-ant-…

# optional: force active provider for smoke
MKLANG_LIVE=1 MKLANG_LIVE_PROVIDER=anthropic uv run --extra dev pytest -q tests/test_live.py

# three-provider gate-divergence (≈12 small Anthropic runs if ×3 on 4 machines)
uv run python scripts/gate_divergence.py --machines all \
  --providers deepseek,openai,anthropic --repeats 3 \
  --summary-json /tmp/gate-div-summary.json \
  --jsonl /tmp/gate-div.jsonl
```

Cost order-of-magnitude: one four-machine × 3-repeat Anthropic pass is on the
order of **~30k tokens / well under $1** (issue #60). Append a results row to
this document (date, providers, per-machine rates) and link the summary JSON
from the PR that records it.

### GitHub Actions (release / optional maintainer workflows)

| Secret name | Required for |
| ----------- | ------------ |
| `DEEPSEEK_API_KEY` | release live matrix (`--require-providers`) |
| `OPENAI_API_KEY` | release live matrix |
| `ANTHROPIC_API_KEY` | third-provider rows; skipped cleanly when absent |
| `TAVILY_API_KEY` | optional search-backed demos/tests, not gate-divergence |

Set repository (or environment) secrets in GitHub → Settings → Secrets and
variables → Actions. The release workflow lists optional providers; without
`ANTHROPIC_API_KEY` those runs are **skipped**, not failed — so missing Anthropic
does not block a DeepSeek+OpenAI release, but it also does **not** close #60.

### Done when

- [ ] Local `.env` has a working key **and** the account has credit
- [ ] One dated three-provider (or Anthropic-including) row is in **Results**
- [ ] Optionally: `ANTHROPIC_API_KEY` is present in Actions secrets for future
      release matrices

## Related

- SPEC §5 (judge protocol), §11 (threat model)
- ADR 0004 (gates as reliability mechanism — empirical claim)
- ADR 0009 (conformance suite pins interpreter rules, not judge accuracy)
- Issues [#60](https://github.com/gianlucamazza/mklang/issues/60),
  [#64](https://github.com/gianlucamazza/mklang/issues/64),
  [#69](https://github.com/gianlucamazza/mklang/issues/69),
  [#72](https://github.com/gianlucamazza/mklang/issues/72)
