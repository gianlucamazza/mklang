# Control-flow-taint incidence

**Question.** How much of a machine corpus can act on a tainted decision — an
effectful `tool:` state reachable via a judge-made choice over external data,
with no `hook:` or human confirmation since (SPEC §6, ADR 0030)?

**Why it matters.** ADR 0030 defaults `on_untrusted_flow` to `report`. ADR 0031
§1 names the condition that would flip the default to `halt` (and force per-state
`effects:` declarations, a 0.4/0.5 surface): **incidence > 0.25** across real
machines, _plus_ author reports. Flipping a safety default on a hunch would be a
language change with no evidence; leaving it on `report` forever without
measuring would be the same mistake in the other direction.

## Metric

```
incidence = flagged effectful tool states / all effectful tool states
```

`flagged` is the lint's own static analysis (`_flow_taint_findings`): a
transition walk marking judged vs confirmed edges; `effectful` follows
`controlflow.TOOL_EFFECTS` with unknown tools effectful by default. Offline and
deterministic — no provider, no key: the number is a property of the documents.

## How to run

```bash
uv run python scripts/taint_incidence.py                # bundled stdlib + examples
uv run python scripts/taint_incidence.py DIR [DIR ...]  # an external corpus
uv run python scripts/taint_incidence.py --json /tmp/taint.json
```

## Results

| Date       | Corpus                                  | Effectful states | Flagged | Incidence | Notes                                                                                             |
| ---------- | --------------------------------------- | ---------------- | ------- | --------- | ------------------------------------------------------------------------------------------------- |
| 2026-08-09 | bundled stdlib + examples (21 machines) | 1                | 1       | 1/1       | `triage.send_reply`, the showcase's real send. **n=1: a floor, not a finding** — see Limitations. |

## Limitations

- **The corpus ADR 0031 §1 is about does not exist here.** The condition reads
  "across real machines" _outside_ this repository, plus author reports. Our own
  corpus has exactly one effectful tool state — the incidence is 1/1 by
  construction of the showcase, and fires nothing. The tool is built so an
  external corpus can be measured unchanged the day one exists (the five-reader
  test, #61, is the same bottleneck: distribution first).
- The lint walk is static and conservative: it cannot see host `overrides`
  reclassifying a tool as read-only, and `call:` resolution needs the registry.
- A flagged state is not a vulnerable state — it is a state whose author has to
  decide (`--untrusted-flow halt`, a `hook:` confirmation, or an accepted risk).
  The metric counts decisions owed, not exploits.
