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

1. A corpus of tasks with **criteria tight enough that the first draft plausibly
   misses** — a machine whose repair gate never fires measures nothing — and loose
   enough that a second draft can pass, since a task nothing can satisfy measures
   the ceiling instead of the repair. It aims at `std_refine` plus three machines
   that exist only to make a repair fire: `exp_strict_format` (countable format
   rules on the entry state), `exp_tighten_middle` (the repair is *not* on the
   entry state) and `exp_compress_lossy` (the failure is dropping a fact, not
   breaking a format rule). Those three live inline in the script, not in
   `src/mklang/data/stdlib/`: they are measuring instruments, and the stdlib is
   1.0 stable surface (ADR 0026). Each routes an exhausted repair through
   `escalate`, never through an `ok` catch-all — the trace reader counts `ok` as
   a pass, so a machine that gave up via `then: ok` would report its own failures
   as successes.
2. Run each item `--repeats N` times against a provider.
3. Read the trace: attempt _k_ of a state is its _k_-th execution; the gate that
   fired says how it went — `repair` → `retry`, `ok` → `pass`, `escalate`/`fail`
   → `give-up` (usually the exhausted budget).
4. Report the pass rate per attempt index, per machine and pooled.

```bash
uv run python scripts/repair_convergence.py --provider deepseek --repeats 5
uv run python scripts/repair_convergence.py --self-check   # offline harness check
```

## Metrics

| Metric                    | Definition                                                        |
| ------------------------- | ----------------------------------------------------------------- |
| `by_attempt[k].reached`   | Runs that executed attempt `k` of a repair state                  |
| `by_attempt[k].pass_rate` | `passes at k / reached k`                                         |
| `lift_attempt_2_over_1`   | `p(2) − p(1)` — **the claim under test**                          |
| `verdict`                 | converging (`lift > 0.05`) / flat / no convergence / not measured |

Reading the verdict:

- **converging** — the feedback is doing something the extra sample alone would
  not.
- **flat** — `repair` is resampling. Not worthless, but the language should stop
  implying self-correction, and `sample: N` + a reducer is the honest comparison.
- **no convergence** — later attempts pass _less_ often. Consistent with the
  selection effect below; not by itself a refutation.

## Limitations

- **The default corpus never exercises a repair.** The one dated run
  (2026-08-09) had all nine attempts pass first time, so `lift` was undefined —
  the harness works, the tasks are too easy. Until it carries states that
  reliably fail attempt 1, `repair`'s claim is unmeasurable, not supported.
- **Selection effect.** Attempt `k` is conditioned on having failed `k−1` times,
  so the surviving population is systematically harder. This biases `lift`
  **downwards**: a positive lift is real evidence, a slightly negative one is
  ambiguous. A stronger design would fix the task set and compare
  repair-with-feedback against re-running the same state with no feedback
  (`repair` vs. plain resample) on identical inputs — worth doing if the first
  numbers are flat.
- **The judge is the ruler.** Pass/fail is the same prose judge whose reliability
  the gate-divergence experiment is separately measuring. A rise in pass rate is
  a rise in _judged_ pass rate.
- **Four machine shapes, one repair loop each.** `std_refine` is the canonical
  shape and `exp_tighten_middle` puts the repair mid-machine, but all four are
  small single-loop machines. A repair inside a longer flow (`std_research`,
  `triage`) may behave differently, so the pooled number is "repair in these four
  machines", not "repair in mklang".

## Results

| Date       | Provider | Runs | p(1)    | p(2) | lift | Verdict                                                 |
| ---------- | -------- | ---- | ------- | ---- | ---- | ------------------------------------------------------- |
| 2026-08-09 | deepseek | 9    | **1.0** | —    | —    | **not measured: too few runs reached a second attempt** |

The 2026-08-09 run is a finding about the corpus, not about `repair`: all nine
runs of `std_refine` passed at attempt 1, so no repair was ever exercised and
`lift` is undefined. The claim stays unmeasurable until the harness has tasks
that reliably fail the first attempt (tracked as a repo issue). Reporting the
run anyway is the point of this table — a green that measured nothing must not
read as evidence.

## Related

- SPEC §5 (`repair(N)` semantics), §7 (budgets and termination)
- [Gate divergence](./gate-divergence.md) — the judge whose verdicts this counts
- ADR 0004 (gates as the reliability mechanism — the empirical claim)
