# ADR 0014 — Structured list outputs: `parse: list` and raw input resolution (0.3)

Status: Accepted

## Context

Two verified 0.2 constraints blocked the last cookbook architecture and limited
machine composition (found while building the stdlib, ADR 0012):

- A generative state always deposits **text**, but `over:` requires a real
  list — so Plan-and-Execute ("planner (list) → `over: {{steps}}` → reducer",
  SPEC §10) was documented but **not implementable** as a single machine.
- `render()` always stringifies, so **lists could not cross a `call:`/`tool:`
  `input:` boundary** — a caller could not hand `std_map_reduce` its `items`.

Both are the same gap: values with structure flowing where 0.2 only moved prose.

## Decision

Language **0.3** — two additive changes, 0.2 documents stay valid:

- **`parse: list`** (new optional generative-state face, SPEC §4.10): the
  produced text is parsed as a **JSON array** (markdown fences tolerated) and
  deposited as a real list. Anything else **halts** with
  `state-error: parse-list …` — never a garbage deposit; the array shape is
  prompted for in `structure`. A 0.2 document using the face draws a `check`
  warning ("declare 0.3"). `"0.3"` joins the supported `mklang:` versions;
  unknown versions still warn (error under `--strict`).
- **Raw whole-template input resolution** (SPEC §4.8/§4.9): an `input:` value
  that is exactly one `{{path}}` placeholder resolves to the **raw** context
  value (list, dict, number) instead of rendering to a string; any mixed
  template renders as before. Non-string YAML input values now pass through
  verbatim too.

Consequently **`std_plan_execute`** joins the stdlib (plan `parse: list` →
execute `over: {{steps}}` → combine) — the eighth machine — and list parameters
can be fed to stdlib machines through `call: input:`.

Conformance pins all three behaviors: `parse-list`, `parse-list-invalid`,
`raw-input-passthrough`. The JSON Schema (both copies) gains the `parse` enum.

## Consequences

- Every cookbook architecture that can be a pure machine now is one; the
  remaining exclusions (ReAct, router, exact policy) are host-dependency
  choices, not language gaps.
- The whole-template rule is a **behavioral change** for a 0.2 document that
  relied on a lone `{{list}}` input value arriving as numbered prose — judged
  vanishingly unlikely (it produced junk downstream) and accepted as part of
  0.3; mixed templates are untouched.
- Parse failures are a halt, not a repair: gates never see unparseable output.
  If field experience wants a repair path, that is a separate decision.
- `parse` stays deliberately minimal (`list` only); `json`/object parsing —
  and with it typed `structure` (§9) — remains open.
