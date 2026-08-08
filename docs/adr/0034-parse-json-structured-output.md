# ADR 0034 — `parse: json`: a produced document is parsed, not trusted

Status: Accepted (2026-08-08)

## Context

`parse: list` (0.3) exists because a planner feeding an `over:` needs a real list,
not prose that resembles one. The same pressure has since accumulated for the
general case, and it is measured in our own machines:

- The console brain carries **five states whose entire job is "turn the previous
  state's prose into JSON"** (`src/mklang/data/console/agent.mkl` —
  `prepare_task_update`, `prepare_workspace_scan`, `prepare_workspace_search`,
  `prepare_workspace_read`, `prepare_run`) — five paid LLM calls per pattern whose
  `structure` reads "A JSON object … and nothing else".
- The platform's example workload declares JSON in prose
  (`workloads/example/machines/expense_note.mkl`: "JSON with keys note, category")
  and its host then gates on **fields of that document** (`mkp:has:output.note`,
  `mkp:in:output.category:…`) — a path grammar reading a document the language
  never promised to produce.
- ADR 0015 pre-committed to reading exactly this signal: _"where `agent.mkl`
  proves clumsy (authoring long documents, structured decisions), that pressure
  feeds the language (e.g. `parse: json`) instead of being hidden in Python."_

## Decision

**`parse: json`** (0.4) on a generative state: the produced text must be valid
JSON (markdown fences tolerated) and the parsed value — object, array or scalar —
is deposited as-is under `output`. Unparseable output halts the state with
`state-error: parse-json …`; a truncated production halts as
`parse-json-truncated` (ADR 0018's rule, per mode). `check` warns when a ≤0.3
document uses the value.

The **shape** of the JSON stays the author's contract — stated in `structure`,
held by the gates. This ADR deliberately does not add a schema language for
outputs: SPEC §9 keeps formal types out of the reliability contract, and the
platform's gate paths plus `parse: json` together already close the observed gap
(the document is real; which fields it has is judged, like everything else).

## Consequences

- One parse dispatch in the engine (`_parse_structured`), sharing the fence
  stripper with `parse: list`; two conformance cases pin deposit and halt.
- The five `prepare_*` states in `agent.mkl` become collapsible into their
  upstream states (a follow-up to that machine, not part of this ADR).
- The platform's `expense_note.mkl` can declare `parse: json` and make
  `mkp:has:output.note` read a guaranteed document — after the interpreter pin
  moves to the release that carries this.
- Not taken: `parse: object` as a distinct stricter mode. Restricting the value
  class is shape, and shape belongs to `structure` + gates; a second enum value
  whose only job is an isinstance check would be the type system §9 declines,
  one key at a time.
