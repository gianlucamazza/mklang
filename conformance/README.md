# mklang conformance suite

Implementation-neutral test cases for the **language semantics** (SPEC §5–§7).
An interpreter conforms to mklang v0.2 when it passes every case in `cases/`
with its own runner. The reference runner is `tests/test_conformance.py`; a
second implementation (TypeScript, Rust, …) writes its own runner against the
same YAML files.

The reference runner is a thin consumer of **`src/mklang/scripttest.py`** — the
single source of truth for the scripted LLM, the scripted `hooks:`/`tools:`
bindings, and the expectation matcher (status / error / `error_prefix` / result /
`at` / trace skeleton / context). The same module powers `mklang test`, which
lets *authors* run their own `.mk` against a script of named scenarios in exactly
this case format (see [README: "Test your machine without API keys"](../README.md)).
The case format below and the `mklang test` scenario format are therefore one
format, matched by one matcher.

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
hooks: # optional scripted gate hooks (host bool predicates, §5)
  over_limit: [false, true] # name -> boolean sequence, one per invocation
tools: # optional scripted tool callables (§4.9)
  search_kb: ["[kb] fact A"] # name -> sequential list, OR a {input-substring: output} map
run: # optional interpreter options (e.g. cost_budget)
  cost_budget: 20
expect:
  status: done | halt # required
  error: <halt reason> # optional — exact match on the kebab-case reason
  error_prefix: <prefix> # optional — startswith match (for reasons with an impl-specific tail)
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
- **hooks**: each `hook: <name>` maps to a boolean sequence; the runtime returns
  the next value per invocation (once one remains, keep returning it). A hook is a
  host predicate `(ctx, output) -> bool` (§5); the case scripts its verdicts.
- **tools**: each `tool: <name>` maps to either a sequential list (returned in
  order) or a `{input-substring: output}` map (the value whose key is a substring
  of the tool input's JSON; error if none match). A tool is a host callable
  `(dict) -> str` (§4.9); the returned string is the observation deposited under
  `output`.

## Scope

Covered: gate policies (ok/repair/escalate/fail), `otherwise`, fused judging,
**hook precedence** (a later hook must not preempt an earlier prose gate — §5
document order), repair budgets, step and cost budgets, **fan-out step charging**
(`max(1, len(branches))`, §7), `call` (incl. failure propagation), fan-out
(`sample` incl. per-branch `{{index}}`, `over`), `accumulate`, **`tool` states**
(observation deposit, unknown-tool halt), result selection, and the halt-reason
taxonomy.

Scripted `hook:`/`tool:` bindings (above) bring hook precedence and tool-state
semantics — genuine language rules, not host behavior — into the suite. Still
excluded (genuinely host behavior): checkpoint/suspend/HITL (ADR 0007/0008),
provider adapters, and trace cost/reasoning annotations. Trace matching is a
skeleton by design — implementations may add annotation keys freely.
