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

1. Fixed synthetic machine: classify a fixed spam-like string into
   `spam` / `ham` / `unknown`, then three prose gates on the label, then a
   trivial terminal path.
2. For each provider in the runtime config that has an API key, run the machine
   (`--repeats N` optional).
3. Record per-run **gate signature**: ordered
   `state|gate|gate_via|to` (not full free-text outputs).
4. Report pairwise `same_signature` and `signature_agreement_rate`.

```bash
uv run python scripts/gate_divergence.py
uv run python scripts/gate_divergence.py --providers deepseek,openai --repeats 3 \
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

| Metric | Definition |
| ------ | ---------- |
| `signature` | Compact routing trace (gates + via + destinations) |
| `same_signature` | Pairwise equality of signatures |
| `signature_agreement_rate` | Fraction of provider pairs that agree |
| `distinct_signatures` | Set of observed routing patterns |

Optional later: majority vote over `N` repeats; Cohen's κ on first-step gate;
temperature ablation.

## Limitations

- Live and non-deterministic; results change with model versions and dates.
- Small synthetic task — not a support-triage benchmark.
- Conformance suite remains the contract for **engine** semantics; this experiment
  is **not** a substitute.
- Cost: one produce + one judge per successful provider (plus short terminal).

## Results

_Not yet filled. Run the script when at least two provider keys are available and
paste a dated summary table here._

| Date | Providers | Agreement rate | Distinct signatures | Notes |
| ---- | --------- | -------------- | ------------------- | ----- |
| —    | —         | —              | —                   | —     |

## Related

- SPEC §5 (judge protocol), §11 (threat model)
- ADR 0004 (gates as reliability mechanism — empirical claim)
- ADR 0009 (conformance suite pins interpreter rules, not judge accuracy)
