# ADR 0008 — Human-in-the-loop: escalate gates that suspend

Status: Accepted

## Context

`escalate` routes to a handler state (SPEC §6) — fine for in-machine escalation
(e.g. a reasoning-tier retry), but "a human decides" needed a way to actually
pause. ADR 0007 shipped checkpoints and reserved `reason: "escalated"` in the
envelope for exactly this.

## Decision

- **Opt-in flag** `escalate_suspend` on `run()` (CLI: `--hitl`, requires
  `--checkpoint`). When a fired `escalate` gate has `to != END`, the runtime sets
  the position to the handler state and **suspends there** — after the transition,
  before the handler runs. Same frames, same envelope (`reason: "escalated"`,
  plus a `hitl: true` marker so `resume` keeps the behavior), exit code 3.
- **Reply injection:** `mklang resume ck.json --set human.reply="…"` writes into
  the **innermost frame's context** before resuming, so the handler state can
  interpolate `{{human.reply}}`. Library callers mutate `frames[-1]["ctx"]`
  directly. No reply is required — resuming without one just runs the handler
  as authored.
- Default off: without the flag `escalate` routes exactly as before, so machines
  using escalate for tier cascades are unaffected even under `--checkpoint`.
- `escalate` to `END` never suspends (nothing downstream could read a reply);
  model a final human sign-off as an escalate to a terminal review state.
- Fan-out branches never suspend (as in ADR 0007): inside a branch the flag is
  forced off and escalate just routes.

## Consequences

- A machine can park indefinitely on a human decision at zero token cost and
  continue exactly where it stopped — nested `call`s included.
- The language is untouched: same schema, same `.mk` files, spec stays 0.2.
  Whether an escalate pauses is a host/run decision, not an author decision;
  if per-gate control turns out to matter, a `hitl:` gate field is the obvious
  later extension.
- The trace keeps a complete audit: the escalate step (with its `when` label),
  then the handler step whose context includes the injected reply.
