# ADR 0010 — LLM-assisted lint (`mklang lint --llm`)

Status: Proposed

## Context

Every static layer mklang ships today reasons about **structure**, never
**meaning**:

- `mklang check` (`semantic_check`) — unknown states, no path to `END`, missing
  tiers, budget infeasibility (R3-2).
- `mklang lint` — dead gates after `otherwise`, repair-only dead ends, unread
  outputs, unresolved `{{interpolation}}` (first segment, plus the second segment
  of inline context maps, R3-3).
- The conformance suite (ADR 0009) — pins the **interpreter**, with a scripted
  LLM. It measures how the *engine* routes given a judge's answer; it never
  measures the *judge*.

None of these can see the single most common prose-authoring failure: two `when`
conditions on the same state that **overlap or are ambiguous**, so which gate
fires depends on the model, the phrasing, or the day. Example:

```yaml
gates:
  - when: the draft resolves the request and is courteous
    then: ok
    to: send
  - when: the draft is acceptable
    repair: 2
    to: draft
```

"resolves and is courteous" ⊆ "acceptable": on a borderline draft the judge may
pick either, and nothing static flags it. This is invisible to structure-only
analysis because both gates are well-formed — the defect is in the *semantics of
the natural-language conditions*, which only a model can evaluate.

The repo already has the machinery to measure exactly this: `scripts/gate_divergence.py`
runs a machine and reduces each run to a **gate-trace signature** (`state|gate|gate_via|to`),
then computes agreement across runs/providers. Today it varies the *provider*; the
same reducer can vary the *synthetic state output* against one machine.

## Decision (proposed — not implemented in 0.5.x)

Add an **opt-in** `mklang lint --llm` that measures gate-selection stability:

1. For each state with ≥2 prose gates, **generate K synthetic outputs** that
   plausibly satisfy the state's `structure` (an LLM call seeded from `structure`
   + the `when` texts, spanning clear-cut and borderline cases).
2. For each synthetic output, **ask the gate judge** which gate fires (the real
   `LLM.judge` path, reused verbatim — this is the same call the engine makes),
   repeated R times.
3. **Reduce to stability/overlap metrics** with the `gate_divergence.py`
   signature machinery:
   - *Instability* — one synthetic output that routes to different gates across
     the R repeats ⇒ ambiguous phrasing.
   - *Overlap* — two `when` conditions that both claim the same outputs ⇒
     redundant or mis-ordered gates.
4. **Report as advisory findings** (never blocking), in the same stream as the
   static lint: `state X: gates 0 and 2 overlap on N/K synthetic outputs`.

### Scope

- **In:** multi-prose-gate states; stability across repeats; pairwise overlap.
- **Out:** hook gates (host predicates, deterministic — nothing to sample);
  `otherwise` (the defined catch-all); anything requiring real context data
  (synthetic outputs only — this is a lint, not a run).

### Cost model

`states_with_multi_prose_gates × (K produce calls + K·R judge calls)`. For a
10-state machine with K=5, R=3, ~5 multi-gate states: ~25 produce + ~75 judge
calls per lint. Real money and latency — hence **opt-in**, gated behind `--llm`,
never part of `mklang check` or the default `mklang lint`, and never wired into
CI's no-network unit path. A `--llm-budget` cap (reusing `cost_budget`) bounds a
single invocation.

### Determinism caveats

The check is inherently **non-deterministic** — that is the point (it measures
variance) — but it means:

- Results are a **signal, not a gate**: `--strict` must not promote `--llm`
  findings to errors. A run-to-run difference in the findings is expected.
- Numbers depend on the provider, tier, and temperature; the report records all
  three (as `gate_divergence.py` already records `judge_model`).
- It can only surface ambiguity it happens to sample. Absence of a finding is not
  proof of unambiguous gates — the report must say so.

### Relation to the conformance suite

Orthogonal, and must not be confused:

- **Conformance (ADR 0009)** measures the **interpreter** — given a judge's
  answer, does the engine route correctly? Scripted LLM, fully deterministic,
  runs offline in CI.
- **`--llm` lint** measures the **judge/author** — are the prose conditions
  themselves stable and non-overlapping? Live LLM, non-deterministic, opt-in.

One pins semantics of the runtime; the other probes the quality of a specific
`.mk`'s prose. Neither substitutes for the other.

## Why out of 0.5.x

- 0.5.x's throughline is **rigor without a key**: conformance, static lint,
  scripted `mklang test` (R3-1) — everything a contributor can run offline in CI.
  A live-LLM lint breaks that property and needs a different support contract
  (keys, cost caps, flaky-result triage).
- The gate-divergence experiment it builds on is still a **scaffold** (ROADMAP:
  agreement rates not yet measured live). Ambiguity-stability numbers are only
  meaningful once single-machine divergence is characterized, so this ADR waits
  on that data.
- It is additive and opt-in: shipping it later changes no existing behavior and
  needs no language change (spec stays 0.2).

## Consequences

- A path exists to catch the prose-authoring failure class no static layer can
  see, reusing the `gate_divergence.py` reducer rather than new machinery.
- The opt-in boundary keeps the offline-CI guarantee intact.
- If adopted, it should land with its own doc note (like the gate-divergence
  experiment) recording cost and interpretation caveats, and must never be a
  `--strict` error source.
