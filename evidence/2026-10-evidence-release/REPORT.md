# Evidence Release 2026-10 — report

Skeleton only. Live rows, summaries, and dollar totals are written after Lab
dispatches `evidence-live.yml`. Nothing in this file is a provider measurement.

## Costs

- **Hard cap (D1):** $10.00 USD across every provider and every named
  experiment in this release.
- **Ledger:** [`costs.jsonl`](./costs.jsonl) — one line per run (`provider`,
  `model`, `input_tokens`, `output_tokens`, `usd`, `usd_source`,
  `price_source`, `price_retrieved`, `run_id`, `github_run_id`, `timestamp`).
- **USD source:** token counts from the provider response × the pinned list
  price in `scripts/cost_ledger.py`. Adapters do not currently expose an
  invoice field; if one appears later, prefer it and set `usd_source` to
  `provider`.
- **Projected cost (no API calls):**

  ```bash
  uv run python scripts/run_evidence_release.py --estimate
  ```

  The table is computed from cited token figures and pinned prices. It is not
  a live invoice. Paste the script output here after the first live dispatch.

| experiment | ledger USD | notes |
| --- | ---: | --- |
| — | — | no live dispatch yet |

## Limits

- Cap check is **before each individual model run** (each provider / machine /
  repeat / arm), not once per named experiment. If
  `ledger total + estimate > $10`, that call is refused (exit 3). After the
  call, the **actual** USD is appended and is what the next run sees — an
  actual above the estimate still counts before the next start.
- `evidence-live.yml` uses `concurrency.group: evidence-live` with
  `cancel-in-progress: false` so two dispatches cannot both read the same
  ledger total and both spend.
- Cross-dispatch accumulation is **enforced**, not procedural. Before the
  live step, the workflow lists `evidence-live.yml` runs (`actions: read` +
  `gh api`) and fails closed unless every prior run that reached
  `Live named experiment` has its `github_run_id` on a checked-out ledger
  row. Merge the artifact `costs.jsonl` from those runs or the next
  dispatch will refuse to start.
- Named experiments and the models they pin live in
  `scripts/run_evidence_release.py` and `config/evidence-release.yaml`.
- Token ceilings already in the harnesses: gate-divergence `cost_budget=20_000`,
  repair-convergence `cost_budget=40_000`.
- Anthropic: there is no `ANTHROPIC_API_KEY`. mklang **can** reach Claude
  through the builtin `openrouter` OpenAI-compatible adapter and model id
  `anthropic/claude-sonnet-5` (already listed as `openrouter.balanced` in
  `config/runtime.example.yaml`). The native `anthropic` adapter is unused
  for this release. If OpenRouter were unavailable, the smallest honest
  option would be to skip the third-provider pass and leave #60 open.

## Negative results

Record misses, skips, and refutations here. Do not infer a language or spec
claim from a green run.

| date | experiment | what failed or was negative | pointer |
| --- | --- | --- | --- |
| — | — | none yet (no live dispatch) | — |

Historical context that is **not** this release's dataset:

- Repair-convergence 2026-08-20 on DeepSeek: `lift` −0.41
  (`docs/experiments/repair-convergence.md`). That is why this release's
  named repair experiment is the second provider.
- Gate-divergence Anthropic is still unmeasured on the native adapter (#60).

## Methods

Named experiments (workflow input `experiment`):

1. `gate-divergence` — seven-machine suite, DeepSeek + OpenAI, 3 repeats.
2. `gate-divergence-anthropic-openrouter` — same seven machines, Claude via
   OpenRouter (`#60`).
3. `repair-convergence` — OpenAI, three arms, full corpus, 3 repeats
   (ADR 0031 §3 second provider).
4. `first-true-live` — one `--live` trial on `priority_shadow` (#126 harness).
5. `estimate` — print the projected-cost table and exit (no API calls).

Raw rows must validate against
[`schema/experiment-result.schema.json`](../../schema/experiment-result.schema.json).
The dated directory is the primary dataset; this Markdown file is a derived
view.
