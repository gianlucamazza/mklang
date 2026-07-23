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
- **Judges:** tier-following (SPEC §2.1 default) — `deepseek-chat` and
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

## Related

- SPEC §5 (judge protocol), §11 (threat model)
- ADR 0004 (gates as reliability mechanism — empirical claim)
- ADR 0009 (conformance suite pins interpreter rules, not judge accuracy)
