# Experiment: does `repair(N)` converge?

## Hypothesis

`repair` re-enters a state with the failed `when` appended to the prompt as
feedback (SPEC §5). The language's claim is that **the feedback makes attempt 2
better than attempt 1** — that this is self-correction, not resampling.

Nothing in the repo measures that. `repair` has shipped since 0.1, appears in six
bundled machines and every cookbook pattern, and its only evidence is that runs
which use it tend to finish.

## Why it matters

If the pass rate does not rise with the attempt index, then:

- the feedback line is decoration, and the reliability comes from **drawing
  another sample** — which a plain retry would buy at the same price;
- the cost is **linear in tokens** for a benefit that could be had with a
  cheaper mechanism (or a smaller `N`, or `sample:` + a reducer);
- the `repair: N` budget is doing the work the prose gate claims credit for, and
  the language should say so instead of implying convergence.

That is a falsifiable claim about a shipped construct, which makes it worth more
than another agreement number.

## Method

Script: [`scripts/repair_convergence.py`](../../scripts/repair_convergence.py).

1. A corpus of tasks aimed at bundled machines with a `repair` gate (today:
   `std_refine`), with **criteria tight enough that the first draft plausibly
   misses** — a machine whose repair gate never fires measures nothing.
2. Run each item `--repeats N` times against a provider.
3. Read the trace: attempt *k* of a state is its *k*-th execution; the gate that
   fired says how it went — `repair` → `retry`, `ok` → `pass`, `escalate`/`fail`
   → `give-up` (usually the exhausted budget).
4. Report the pass rate per attempt index, per machine and pooled.

```bash
uv run python scripts/repair_convergence.py --provider deepseek --repeats 5
uv run python scripts/repair_convergence.py --self-check   # offline harness check
```

## Metrics

| Metric                 | Definition                                                       |
| ---------------------- | ----------------------------------------------------------------- |
| `by_attempt[k].reached` | Runs that executed attempt `k` of a repair state                  |
| `by_attempt[k].pass_rate` | `passes at k / reached k`                                       |
| `lift_attempt_2_over_1` | `p(2) − p(1)` — **the claim under test**                          |
| `verdict`              | converging (`lift > 0.05`) / flat / no convergence / not measured  |

Reading the verdict:

- **converging** — the feedback is doing something the extra sample alone would
  not.
- **flat** — `repair` is resampling. Not worthless, but the language should stop
  implying self-correction, and `sample: N` + a reducer is the honest comparison.
- **no convergence** — later attempts pass *less* often. Consistent with the
  selection effect below; not by itself a refutation.

## Limitations

- **No live rows yet.** The harness and its offline self-check are in; no dated
  provider run has produced numbers. Nothing here is a finding yet.
- **Selection effect.** Attempt `k` is conditioned on having failed `k−1` times,
  so the surviving population is systematically harder. This biases `lift`
  **downwards**: a positive lift is real evidence, a slightly negative one is
  ambiguous. A stronger design would fix the task set and compare
  repair-with-feedback against re-running the same state with no feedback
  (`repair` vs. plain resample) on identical inputs — worth doing if the first
  numbers are flat.
- **The judge is the ruler.** Pass/fail is the same prose judge whose reliability
  the gate-divergence experiment is separately measuring. A rise in pass rate is
  a rise in *judged* pass rate.
- **One machine shape.** `std_refine` is the canonical repair loop; the corpus
  should grow to a `repair`-in-the-middle machine (`std_research`, `triage`)
  before the pooled number is quoted as "repair in mklang".

## Results

_No live run recorded yet._ Add a dated row (provider, repeats, per-attempt
rates, verdict) and link the summary JSON from the PR that records it.

| Date | Provider | Runs | p(1) | p(2) | lift | Verdict |
| ---- | -------- | ---- | ---- | ---- | ---- | ------- |
| —    | —        | —    | —    | —    | —    | not measured |

## Related

- SPEC §5 (`repair(N)` semantics), §7 (budgets and termination)
- [Gate divergence](./gate-divergence.md) — the judge whose verdicts this counts
- ADR 0004 (gates as the reliability mechanism — the empirical claim)
