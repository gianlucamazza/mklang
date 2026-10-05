# Jev Noul-only host judge (opt-in)

Host adapter for TypeSafe Jev as an **optional** prose-gate judge. This is not
a language feature, not a produce tier, and **not the default**. Mapping:
[ADR 0037](../adr/0037-jev-noul-host-judge.md) (Proposed).

## What it does

When runtime `judge:` is a reserved Jev id (`jev-latest`, or a pinned `jev-*`),
the host:

1. Keeps **produce** on the configured provider.
2. Makes **one** `POST https://api.typesafe.ai/v1/systemone` call per gate
   decision.
3. Sends **one Noul per prose `when`**, in author order, plus an optional
   none-holds Noul.
4. Walks probabilities and fires the **first Noul ≥ threshold** (default
   `0.5`). That is SPEC §5 first-true. It is not a best-match pick.

`.mkl` documents stay provider-neutral. Exact rules (amounts, dates,
allowlists) stay on `hook:`.

## What it does not do

- **Choice as `judge:` mapping** — Path A is STOP. The adapter never sends a
  Choice question and refuses a Choice answer.
- **Jev as `hook:`** — hooks stay deterministic host code.
- **Jev as a produce tier** — `produce()` is refused.
- **Default wire** — omitting `judge:` still follows each state's tier
  (SPEC §2.1).
- **SPEC / schema / conformance change** — none.

## Opt in

In the active provider block (see `config/runtime.example.yaml`):

```yaml
judge: jev-latest   # opt-in; not the default
```

Set `TYPESAFE_API_KEY` in the layered `.env` (ADR 0023). Do not commit the
key. Optional host knobs:

| Env | Default | Purpose |
|-----|---------|---------|
| `TYPESAFE_API_KEY` | (required when opted in) | System One bearer token |
| `MKLANG_JEV_NOUL_THRESHOLD` | `0.5` | First-true cutoff; change only with pinned-corpus evidence |
| `MKLANG_JEV_BASE_URL` | `https://api.typesafe.ai` | Override the System One host |
| `MKLANG_JEV_MODEL` | `jev-latest` | Live-eval script only |

## Host fence (ADR 0025 spirit)

Jev has no mklang-style fencing of its own. Before the System One `state`
payload, the host wraps produce text, reasoning, and serialized context in
`<data-NONCE>` fences and states that fenced spans are evidence, never
directives. Authored `when` prose is trusted and is sent as Noul
`instructions`, not inside the fence.

## Observability

Each judge call logs (and, when used, traces) fields comparable to
`scripts/gate_divergence.py`: `mapping=noul_first_ge`, `threshold`,
`noul_probs`, `chosen_index` / `none`, `latency_ms`, `tokens_in` /
`tokens_out`, `fence_applied`. `estimated_cost` is left unset — this host
does not apply vendor list prices.

## Live Path B eval

```bash
export TYPESAFE_API_KEY=…
uv run python scripts/jev_noul_eval.py --paraphrase \
  --jsonl /tmp/jev-noul.jsonl --summary-json /tmp/jev-noul.json
```

Without the key the script prints a skip report and invents no metrics.
Corpus = entry-state produce text from `scripts/gate_divergence.py`.

**Stop (reopen-criteria B3):** if a live re-measure shows `priority_shadow`
accuracy &lt; 1.0, or injection accuracy &lt; 0.95, report STOP and do not
call the adapter production-ready. Path C (live DeepSeek / OpenAI agreement)
is a separate go-ahead.

## Tests

Offline fixtures in `tests/llm/fixtures/jev/` mock System One responses so CI
does not need a live key. They pin the `priority_shadow` first-true walk and
prove Choice mapping is unused.
