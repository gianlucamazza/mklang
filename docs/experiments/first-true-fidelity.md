# Experiment: first-true fidelity vs prompt-spaghetti

## Hypothesis

mklang's host turns overlapping prose gates into a single transition by a
**first-true walk** (SPEC §5): conditions are scanned in document order and the
first accepted gate fires. A prompt-spaghetti baseline — one unordered /
best-match pick with **no** host walk — will miss that rule on
`priority_shadow`, where an earlier broad condition and a later narrower one
both hold.

This is an **eval**, not a product path. It does not add Choice-as-`judge:` to
the language and it does not ship a Jev adapter.

## Methods

> We evaluate first-true gate routing on the pinned gate-divergence corpus
> shipped with mklang (`scripts/gate_divergence.py`). Arm A walks gate
> conditions in document order and fires the first accepted condition. Arm B
> uses a single unordered multi-option prompt (prompt-spaghetti) with no host
> first-true walk. We report per-machine accuracy and, on `priority_shadow`,
> first-true fidelity. Produce texts and gold routes are pinned by content
> hash; commands and tip SHA are listed in the artifact README.

Script: [`scripts/first_true_eval.py`](../../scripts/first_true_eval.py).
Pinned produce texts / gold `to:` / oracle `holds`:
[`scripts/fixtures/first_true_eval.json`](../../scripts/fixtures/first_true_eval.json).
Machines come from [`scripts/gate_divergence.py`](../../scripts/gate_divergence.py)
(entry-state gates only).

### How to run

```bash
# Offline dry-run (default; CI). Oracle holds, no provider keys.
uv run python scripts/first_true_eval.py
uv run python scripts/first_true_eval.py --self-check \
  --jsonl /tmp/first-true.jsonl --summary-json /tmp/first-true-summary.json

# Optional wording variants (labeled separately; same produce and gold).
uv run python scripts/first_true_eval.py --paraphrase

# Live judge (needs a provider key in .env). Propose 2 reps. Not used by CI.
uv run python scripts/first_true_eval.py --live --provider deepseek --repeats 2 \
  --jsonl /tmp/first-true-live.jsonl --summary-json /tmp/first-true-live.json
```

The summary JSON records `fixture_hash` (SHA-256 of the pin file) and
`tip_sha` (repo `git rev-parse HEAD` when a checkout is present). Quote both
with the command above.

### Arms

| Arm | Protocol |
| --- | --- |
| **A** `first_true` | Host first-true. Mock: first holding `when:` in document order, else `otherwise`. Live: fused `LLM.judge` in author order with the none option (the interpreter's SPEC §5 batch), falling through to `otherwise`. |
| **B** `prompt_spaghetti` | Single unordered / best-match pick. Mock: **last** holding author condition (later / narrower), else `otherwise`. Live: one `produce` prompt that lists every `when:` as an unordered set and asks for a single choice — **not** `LLM.judge`, which is first-true by construction. |

Do not call arm B "Jev". If a later run uses a Jev Choice as B, cite the G2
receipt and keep Choice-as-`judge:` STOP.

### Corpus pin

Default machines: `gate_divergence`, `priority_shadow`, `none_holds`,
`threshold_edge`. The fixture also pins `severity_escalate` (`--machines all`).
Produce strings are exact; the mock never calls a model to generate them.
Gold `to:` is the first hop of `GOLD` in `scripts/gate_divergence.py`.
`--paraphrase` adds the suite's existing wording variants as separately
labeled rows.

## Metrics

| Metric | Definition |
| --- | --- |
| Accuracy | `pred_to == gold_to` per trial, per arm |
| `priority_shadow` fidelity | On that machine only: `acc_first_true`, `acc_spaghetti`, and `first_true_wins` (A correct and B not) |
| n | Trials per machine × `--repeats` (propose 2 if live) |
| Fail modes | `wrong_to`, `none_abstain`, `unparseable` |
| Latency / tokens | Logged **only** on `--live` rows (`metrics.latency_ms`, `usage`). No invented vendor speed or € |

Report table columns: machine, condition count, n, acc_A, acc_B, fail modes,
notes.

## Results

No live row yet. The offline dry-run is a harness check: with the pinned
oracle, arm A matches gold on every fixture machine and arm B misses
`priority_shadow` (narrower second gate). That is the expected mock shape, not
a provider measurement.

| Date | Mode | Notes |
| --- | --- | --- |
| — | mock | CI dry-run only. Do not quote as model evidence. |

## Related

- SPEC §5 (first-true selection, totality)
- [Gate divergence](./gate-divergence.md) — the corpus this eval pins
- Issue [#120](https://github.com/gianlucamazza/mklang/issues/120)
