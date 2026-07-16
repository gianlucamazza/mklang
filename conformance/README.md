# mklang conformance suite

Implementation-neutral test cases for the **language semantics** (SPEC §5–§7).
An interpreter conforms to mklang v0.2 when it passes every case in `cases/`
with its own runner. The reference runner is `tests/test_conformance.py`; a
second implementation (TypeScript, Rust, …) writes its own runner against the
same YAML files.

## Case format (`cases/*.yaml`)

```yaml
case: <slug> # must match the filename stem
description: <one line — which semantic rule this pins down>
machine: { ... } # an inline mklang machine (same shape as a .mk file)
registry: # optional: extra machines resolvable by `call`
  <name>: { ... }
llm: # the scripted LLM (see contract below)
  produce: ["text", ...] # list → sequential; or a map {prompt-substring: text}
  tokens: [in, out] # optional: cost charged per produce (default [0, 0])
  judge: [0, 1, ...] # sequential judge picks; or the string "unparseable"
run: # optional interpreter options (e.g. cost_budget)
  cost_budget: 20
expect:
  status: done | halt # required
  error: <halt reason> # optional — exact match on the kebab-case reason
  result: <value> # optional — exact match
  at: <state> # optional — where the run halted
  trace: # optional — SKELETON match: same number of steps,
    - { state: a, policy: ok, to: b } # each listed key must equal the step's value
  context: # optional — exact match per listed key
    notes: ["…"]
```

## Scripted-LLM contract

The runner must provide an LLM whose behavior is fully determined by the case:

- **produce** (list form): return the texts in order, one per generative
  execution. Deterministic only on linear paths — fan-out cases use the map form.
- **produce** (map form): return the value whose key is a substring of the
  rendered user prompt; error if nothing matches.
- **tokens**: every produce reports this `[input, output]` cost (drives the
  cost-budget cases). Default zero.
- **judge**: return the listed indices in order (an index into the presented
  condition batch); once one entry remains, keep returning it. The string
  `"unparseable"` means every judge call fails as unparseable (SPEC §7:
  soft-fallback to an eligible `otherwise`, else halt `judge-unparseable`).

## Scope

Covered: gate policies (ok/repair/escalate/fail), `otherwise`, fused judging,
repair budgets, step and cost budgets, `call` (incl. failure propagation),
fan-out (`over`), `accumulate`, result selection, and the halt-reason taxonomy.

Excluded (host behavior, not language): checkpoint/suspend/HITL (ADR 0007/0008),
`tool` states and `hook:` gates (they need host bindings), provider adapters,
trace cost/reasoning annotations. Trace matching is a skeleton by design —
implementations may add annotation keys freely.
