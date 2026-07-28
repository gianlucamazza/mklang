# mklang conformance suite

Implementation-neutral test cases for the **language semantics** (SPEC §5–§7).
An interpreter conforms to mklang v0.3 (v0.2 documents remain valid) when it
passes every case in `cases/` with its own runner. The reference runner is `tests/conformance/test_conformance.py`; a
second implementation (TypeScript, Rust, …) writes its own runner against the
same YAML files.

The reference runner is a thin consumer of **`src/mklang/scripttest.py`** — the
single source of truth for the scripted LLM, the scripted `hooks:`/`tools:`
bindings, and the expectation matcher (status / error / `error_prefix` / result /
`at` / trace skeleton / context). The same module powers `mklang test`, which
lets _authors_ run their own `.mkl` against a script of named scenarios in exactly
this case format (see [README: "Test your machine without API keys"](../README.md)).
The case format below and the `mklang test` scenario format are therefore one
format, matched by one matcher.

## Case format (`cases/*.yaml`)

```yaml
case: <slug> # must match the filename stem
description: <one line — which semantic rule this pins down>
machine: { ... } # an inline mklang machine (same shape as a .mkl file)
registry: # optional: extra machines resolvable by `call`
  <name>: { ... }
llm: # the scripted LLM (see contract below)
  produce: ["text", ...] # list → sequential; or a map {prompt-substring: text}
  tokens: [in, out] # optional: cost charged per produce (default [0, 0])
  judge: [0, "none", ...] # sequential judge picks; "none" = no condition in the
  # batch holds (SPEC §5, falls through); or the string "unparseable" for the whole run
hooks: # optional scripted gate hooks (host bool predicates, §5)
  over_limit: [false, true] # name -> boolean sequence, one per invocation
tools: # optional scripted tool callables (§4.9)
  search_kb: ["[kb] fact A"] # name -> sequential list, OR a {input-substring: output} map
input: # optional host-supplied context, merged over `context:` —
  task: "…" # tainted by provenance (SPEC §6, ADR 0025)
run: # optional interpreter options (e.g. cost_budget)
  cost_budget: 20
  on_untrusted_flow: halt # control-flow-taint policy (SPEC §6): report (default) | halt
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
- **produce** (map form): return the value whose key is a **first match wins**
  substring of the rendered user prompt (map order); error if nothing matches.
  Tainted interpolations arrive fenced (SPEC §6): match the stable `<data-`
  prefix to assert delimiting, or order a `<data-` key first and a bare-text
  key second to assert its _absence_.
- **tokens**: every produce reports this `[input, output]` cost (drives the
  cost-budget cases). Default zero.
- **judge**: return the listed indices in order (an index into the presented
  condition batch); once one entry remains, keep returning it. The string
  `"none"` is the **none of the above** verdict (SPEC §5 _Totality_: every
  condition in that batch is false, so evaluation continues at the gate after
  the batch); an implementation surfaces it as the extra `N+1` option and its
  runner must accept it wherever an index is accepted. The string
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
document order), **transition totality** (§5: a `none` verdict falls through to
the next gate — catch-all or hook — and off the end of the gate list halts
`no-gate-matched`; an unresolvable `hook:` halts rather than reading as False),
repair budgets, step and cost budgets, **fan-out step charging**
(`max(1, len(branches))`, §7), `call` (incl. failure propagation), fan-out
(`sample` incl. per-branch `{{index}}`, `over`), `accumulate`, **`tool` states**
(observation deposit, unknown-tool halt), **output parsing** (0.3 `parse: list`:
JSON-array deposit for downstream `over:`, and the clean state-error halt on
non-array output), **raw input resolution** (0.3: an `input:` value that is
exactly one `{{path}}` placeholder passes the raw context value — e.g. a list —
into the callee; mixed templates still render text), result selection, the
halt-reason taxonomy, and **untrusted-context delimiting** (SPEC §6 / ADR 0025: the four
`taint-*` cases pin fenced tool observations, host inputs, and call results,
plus bare author literals), plus **control-flow taint** (SPEC §6 / ADR 0030: the
five `flow-taint-*` cases pin the marked decision, the effect-surface boundary,
the `hook:` confirmation, the `halt` policy, and that a `call:` does not launder
the tainted decision away from the sub-machine's effect). Judge-prompt fencing is adapter
behavior → unit tests, not conformance.

Scripted `hook:`/`tool:` bindings (above) bring hook precedence and tool-state
semantics — genuine language rules, not host behavior — into the suite. Still
excluded (genuinely host behavior): checkpoint/suspend/HITL (ADR 0007/0008),
provider adapters, and trace cost/reasoning annotations. Trace matching is a
skeleton by design — implementations may add annotation keys freely.

## What conformance does and does not guarantee

Every case in this suite runs against a **scripted** LLM: the produce texts and
the judge's verdicts come from the case file, not from a model. That is what
makes the suite a specification instead of a benchmark — and it fixes exactly
how far a passing result reaches.

**Conformance pins the mechanical skeleton.** Two conformant interpreters, given
the same machine and the same sequence of oracle verdicts, produce the same
trace: same states in the same order, same gate selected, same deposits, same
budget arithmetic, same halt reason, same taint marks. Everything that is a
function of the machine plus the verdicts is nailed down.

**It does not pin behaviour in production.** In a real run the verdicts come from
a model, and the model is not part of the contract. So two conformant runtimes
can diverge arbitrarily on the same `.mkl` and the same input — different
provider, different model version, or the same model on a different day
(measured: `docs/experiments/gate-divergence.md`). Concretely, passing this suite
says **nothing** about:

- **which** gate a prose condition will fire on any given input — only what the
  runtime must do once a verdict exists;
- whether two providers, or two runs of one provider, agree;
- whether a `repair` loop converges (`docs/experiments/repair-convergence.md`);
- output quality, latency, or cost;
- anything a `hook:` or `tool:` does — the suite scripts their return values, so
  it pins how the runtime _uses_ a host predicate, never what the host computes.

So the accurate claim for a second implementation is: **"it matches the
language's mechanical contract."** Not "it behaves the same." A machine whose
outcome must hold across runtimes needs its consequential transitions on
`hook:` gates or human review (SPEC §5, §8 _What a trace attests_, §11) — the
conformance suite is what makes those hooks compose identically everywhere, not
a substitute for them.
