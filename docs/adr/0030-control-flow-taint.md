# ADR 0030 — Control-flow taint: the taint follows the choice

Status: Accepted

## Context

ADR 0025 made untrusted values structurally distinguishable from instructions:
tainted interpolations ride `<data-NONCE>` fences in produce prompts, the judge's
OUTPUT / REASONING / CONTEXT are fenced unconditionally, and the model is told
fenced spans are evidence, never directives. That closed the *reading* half of
SPEC §11's declared gap.

It left the other half open, and the fences make its shape precise: **the gate
judge reads tainted content and from it chooses the transition.** The judge's
verdict is control flow. A machine that pulls a web page, judges "the request is
resolved and safe to send", and routes into a `send_reply` tool state can be
steered by that page — and no invariant is violated when it happens. The
reasoner is committing reality, and the language has nothing to say about it. A
stronger fence cannot fix that, because the failure is not the model confusing
data with instructions; it is a legitimate decision made from poisoned evidence.

Two existing pieces are half the answer and were the tempting places to stop:

- **ADR 0017 Layer 2 “context zones”** would separate untrusted regions of the
  blackboard. Necessary, not sufficient: zoning the *text* still lets a judge
  reading the untrusted zone pick the effectful branch.
- **SPEC §11 author discipline** (“put high-stakes transitions on hooks”) is
  correct advice with no enforcement, no static check, and no trace evidence.

## Decision

Propagate taint onto the **choice**, and bind the rule at the **effect surface**.
Normative in SPEC §6 (“Control-flow taint”).

### 1. A narrower taint class: `external`

The existing tainted set cannot carry this rule. Under ADR 0025 *every* deposit
is tainted — produce output is oracle-derived even from author literals — so
after one state, everything is tainted and a rule keyed on it would fire on every
prose gate in every machine, i.e. mean nothing.

So the engine tracks `external ⊆ tainted`: keys carrying data that came from
outside the run. Host-supplied inputs are external at start; tool observations
always are; a `call` result is external if an input carries external data or the
sub-machine can reach a tool state; a generative output is external iff its
prompt, `over:` source, or fan-out item interpolated something external.

### 2. A tainted decision is a run-level fact

A transition is tainted when a judge selected it while any external key was in
scope. Scope is the whole blackboard on purpose: the judge is shown OUTPUT plus
the CONTEXT blob, so one poisoned value anywhere is evidence it read. The flag
persists (`flow_tainted`), is recorded on the deciding step as
`decision_tainted`, and is cleared by exactly two things: a `hook:` gate (host
code chose that transition) and a human reply injected at resume
(`human.reply` present under ADR 0008 — a bare `human` key is not confirmation).
`otherwise` neither sets nor clears — a default is not a confirmation.

### 3. The rule binds at the effect surface

Only `tool:` states can act on the world (generative `execution` cannot invoke
host tools), so the effect surface is exactly the tool registry, classified
read-only vs effectful in `controlflow.TOOL_EFFECTS`. **Unclassified tools —
every third-party plugin — count as effectful**: silence is not a safety claim.
Hosts classify their own via `run(..., tool_effects=...)`.

A tainted decision reaching an effectful tool state is always **recorded**
(`untrusted_control_flow: true`). Whether it is **refused** is host policy:
`report` (default) or `halt` (`--untrusted-flow halt`), which halts with
`untrusted-control-flow` before the tool runs.

### 4. Static counterpart

`mklang lint` walks the transition graph and reports effectful tool states
reachable from a prose-gated decision with no `hook:` on the path. It is a
`note:` (advisory under `--strict`): a machine whose context is entirely
author-controlled has nothing to inject, and only the author knows that.

## Alternatives considered

- **Refuse at the gate instead of at the effect.** "A tainted gate may not select
  a transition into an effectful state" needs the destination's effect status at
  selection time, which misses the common shape — route to a produce state that
  unconditionally routes to the tool. Checking on *entry* to the effect catches
  both and needs no reachability analysis at run time.
- **A new `effects: true` state field.** Cleaner to read, but it is a language
  change, and language 0.3 is frozen (ADR 0026): it would need a 0.4 and a
  conformance cycle for something derivable from the tool name. Reconsider if
  hosts find the registry classification too coarse.
- **Halt by default.** Correct destination, wrong release. Defaulting to `halt`
  would break running machines (e.g. `examples/triage.mkl`) on a behaviour rule
  that has never been observed in the field. `report` makes it measurable first;
  see the falsification note in ADR 0031 for what would force the flip.
- **Do nothing until context zones ship.** Zones are a bigger, later change and
  address the reading half. Waiting would leave the enforceable half unbuilt.

## Consequences

- Positive: the injection story now has an invariant, not only advice — and
  three places that fail loudly (trace, lint, halt policy) instead of one
  paragraph of guidance.
- Positive: the fix an author is pushed toward (`hook:` on the transition into
  the effect) is the same thing SPEC §11 already recommended, now checkable.
- Negative: `external` is an over-approximation (a `call` into any
  tool-reaching machine, the whole blackboard as judge scope). False "external"
  costs one confirmation gate; false "trusted" costs the invariant — the
  asymmetry is deliberate.
- Negative: not a dual control plane. A tainted decision routing into a
  *generative* state is unconstrained; the judge still reads untrusted content.
  This bounds what an injection can **cause**, not what it can **say**.
- Follow-up: revisit `halt` as the default in language 0.4; revisit
  per-state effect declarations if the registry classification proves too coarse;
  ADR 0017 Layer 2 zones remain the complementary work.
