# ADR 0035 — An escalate gate carries its own ask

Status: Accepted (2026-08-08)

## Context

Under HITL suspension the language tells a host _that_ a run parked and _where_
(`error: escalated`, `at:`), but not **what to put in front of the human** or
**where the reply lands**. Both gaps are filled today by hosts, badly:

- The platform's queue projection is reduced to a placeholder — its own code
  reads `summary = f"Needs a decision on step {step_id}"` with an explicit
  `del commission_out  # never read machine output for summary` — because the
  only text available at park time is machine output, which its operator UI
  rightly refuses to display (mklang-platform `wait_projection.py`,
  `operator-web.md`: "The 'ask' is invisible … degraded queue without ask is not
  the product").
- The reply path is a host constant standing in for a language name:
  `HUMAN_REPLY_PATH = "human.reply"` with the comment _"a machine's `escalate`
  gate has to be written against a name, and inventing one per workflow would
  make machines unportable"_ (mklang-platform `mklang_host.py`). The machine is
  written against a name the language never defined.

Both are authored knowledge: what to ask, and where the machine reads the
answer, are decided by whoever wrote the gate — a host cannot know them from
outside. That is ADR 0031's condition-1 shape, same as `max_visits` (ADR 0033).

## Decision

Two optional fields on **escalate gates only** (schema-enforced), 0.4:

1. **`ask: <string>`** — what to put in front of the human. **Literal, never
   interpolated**: an ask that embedded `{{context.*}}` would carry
   model-derived (tainted) text into the one surface hosts must be able to
   trust for display. The ask comes from the signed document, so a host may
   render it where machine output is untrusted — which is precisely why it must
   be a language field and not a host heuristic.
2. **`reply_to: <context key path>`** — where the reply lands on resume.
   Default **`human.reply`**: the name existing machines and hosts already use,
   now owned by the language instead of re-invented per host.

Mechanics: under HITL suspension both ride the suspended `RunResult` (additive
wire keys `ask`, `reply_to`) and the checkpoint frame (additive keys; pre-0.4
frames resume unchanged and keep the default). The resume-confirmation rule
(ADR 0030) follows the frame's `reply_to` — a reply at the default path does
not confirm a gate that named another.

## Consequences

- Engine: the escalate-suspend path annotates the frame and the result;
  `_human_confirmed` generalizes from the hard-coded `human.reply` to the
  frame's path. One conformance case (`escalate-ask`) pins suspension payload;
  the scenario matcher learns `ask`/`reply_to`.
- The platform can build a real queue row from authored text without touching
  machine output, and delete `HUMAN_REPLY_PATH` in favour of the result's
  `reply_to` — after its interpreter pin moves.
- Not taken: interpolation in `ask:` (breaks the display-safety property that
  justifies the field) and a structured reply schema (the reply is context like
  any other; its shape is the handler state's contract).
