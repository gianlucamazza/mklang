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
2. For each selected machine and each provider in the runtime config with an
   API key, run it (`--repeats N` optional).
3. Record per-run **gate signature**: ordered `state|gate|gate_via|to` (not
   full free-text outputs).
4. Report pairwise `same_signature` and `signature_agreement_rate`, **computed
   within each machine** (cross-machine signatures differ by construction), plus
   a `per_machine` breakdown. The release gate enforces `--min-agreement`
   per-machine so no single machine hides behind a high pooled average.

```bash
uv run python scripts/gate_divergence.py
uv run python scripts/gate_divergence.py --machines all --providers deepseek,openai --repeats 3 \
  --jsonl /tmp/gate-div.jsonl
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

| Metric                     | Definition                                           |
| -------------------------- | ---------------------------------------------------- |
| `signature`                | Compact routing trace (gates + via + destinations)   |
| `same_signature`           | Pairwise equality of signatures                      |
| `signature_agreement_rate` | Fraction of within-machine provider pairs that agree |
| `per_machine`              | Same metrics broken down per suite machine           |
| `distinct_signatures`      | Set of observed routing patterns                     |

Optional later: majority vote over `N` repeats; Cohen's κ on first-step gate;
temperature ablation.

## Limitations

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
