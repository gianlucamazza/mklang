# Authoring guide

A compact recipe for writing a correct `.mk` — aimed at LLM agents and humans who
want the happy path without reading the full [SPEC](../SPEC.md) first. This page
distills; it does not replace. Tuning advice lives in [Patterns](patterns.md).

## The recipe

1. Start from the skeleton below (or the closest [example](#which-example-to-copy)).
2. Fill the faces state by state; every path must reach `END` within `budget`.
3. Validate: `mklang check my.mk` (schema + semantics), then `mklang lint my.mk`
   (dead gates, unread outputs, typos).
4. Pin behavior without keys: `mklang test my.mk --script my.test.yaml`.
5. Run: `mklang run my.mk --set key=value` — or commission it from an MCP host
   via the `run` tool (`mklang-mcp`, inline source or path).

## Skeleton

Start every file with the schema header — editors and agents get validation for free:

```yaml
# yaml-language-server: $schema=../schema/mklang.schema.json
mklang: "0.2"
machine: my_machine # identifier (snake_case)
entry: first_state # where the run starts
budget: 6 # max steps per run — shortest path + headroom (see below)
result: answer # context key returned to the caller (default: last output)
context: # initial blackboard (optional); --set / inputs merge here
  question: ""
states:
  first_state:
    structure: a short answer, max 50 words # what shape?
    prompt: "Answer: {{question}}" # what to think?
    output: answer # stored under this context key
    gates:
      - when: the answer addresses the question
        then: ok
        to: END
      - when: otherwise # ALWAYS end with a catch-all
        repair: 2
        to: first_state
```

Required top-level keys: `machine`, `entry`, `budget`, `states`. A state is
**exactly one** of generative (`prompt`), call (`call`), or tool (`tool`).

## The faces of a state

Core (generative states — SPEC §4):

| Face        | Answers        | Notes                                                |
| ----------- | -------------- | ---------------------------------------------------- |
| `structure` | what shape?    | prose contract for the output                        |
| `prompt`    | what to think? | the task, with `{{context.key}}` interpolation       |
| `execution` | how to act?    | optional operational policy — **never** side effects |
| `gates`     | when to exit?  | the transition table (below)                         |

Optional faces — reach for them when the pattern calls for it:

- `reason: true` — private chain-of-thought, captured in the trace (§4.5).
- `accumulate: true` — append to a list under `output` instead of overwriting (§4.6).
- `sample: N` / `over: "{{list}}"` — fan-out; output becomes a list; mutually
  exclusive; `{{index}}` available inside both, `{{item}}` inside `over` (§4.7).
- `parse: list` — deposit a parsed JSON array instead of text, ready for a
  downstream `over:`; declare `mklang: "0.3"` (§4.10).
- `call: <machine>` — run a sibling machine as a subroutine; `input:` maps parent
  context in, `output:` receives its `result` (§4.8).
- `tool: <name>` — a host-registered callable; the **only** place for real side
  effects (search, send, calc) (§4.9).

## Gates are the transitions

Each gate is a prose condition the LLM judges (or a deterministic `hook:`), plus
exactly one policy (SPEC §5):

| Policy           | Effect                                           |
| ---------------- | ------------------------------------------------ |
| `then: ok`       | advance to `to:` (`END` finishes the run)        |
| `repair: N`      | re-run this state with feedback, at most N times |
| `escalate: true` | route to a handler state (suspends under HITL)   |
| `fail: true`     | abort the run                                    |

Rules of thumb:

- Multi-gate states need a `when: otherwise` catch-all **last** — gates after it
  are dead, and without it an unmatched judgment halts the run.
- A state whose only exits are `repair` is a guaranteed halt once the repair
  budget runs out — always pair it with an `ok`/`escalate`/`fail` route.
- Exact checks (thresholds, format, policy) belong in a `hook:` gate, not prose.

## Budget

`budget` counts steps (states entered). Set it to the shortest `entry → END`
path plus headroom for loops and repairs: `check` rejects `budget-infeasible`
(below the shortest path) and warns when there is no headroom. A fan-out state
charges one step per branch at runtime but counts as 1 at check time.

## Hard rules

- **Never name a provider or model in a `.mk`** — route by `tier:`
  (`fast` / `balanced` / `reasoning`) only; the host config maps tiers to models
  (ADR 0003).
- **No side effects in prose.** `execution` is policy, not action; anything that
  touches the world is a `tool:` state.
- Every `{{key}}` must resolve: from `context:`, a previous state's `output:`,
  `human.*` (HITL resume), or `item`/`index` inside a fan-out state.
- `call:` targets must exist as sibling `.mk` files (same directory) — an inline
  MCP `source` machine can only call machines it ships with.

## What the validators catch

`mklang check` errors (blocking) and warnings you will actually see:

```text
entry 'x' is not a state
draft: gate -> unknown state 'sendd'            # typo in to:
combine: call -> unknown machine 'summarize'    # missing sibling .mk
no reachable path to END
budget-infeasible: budget 2 is below the 4-step shortest path to END
draft: no 'otherwise' catch-all gate            # warning
result key 'answr' is not produced by any state's output   # warning
```

`mklang lint` adds static smells: dead gates after `otherwise`, repair-only
states, outputs never read, and `unresolved-interpolation` (a `{{key}}` whose
root is no context key or output — typos like `{{ticket.bod}}` included).
`--strict` promotes lint findings to failures.

## Which example to copy

Before writing a generic architecture yourself, check the [machine stdlib](stdlib.md):
CoT, self-consistency, refine, ToT, debate, map-reduce and cascade ship as ready
`std_*` machines you can `call:` or run by name.

| Pattern                                    | Example                                                                                                 |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Minimal single state                       | [`summarize_doc.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/summarize_doc.mk)       |
| Branching FSM + real tools + scenario test | [`triage.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/triage.mk)                     |
| Reason/act/observe loop (`accumulate`)     | [`react.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/react.mk)                       |
| Iterative loop with sufficiency gate       | [`research.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/research.mk)                 |
| Fan-out `sample` + reducer                 | [`self_consistency.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/self_consistency.mk) |
| `over` + `call` orchestration              | [`map_reduce.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/map_reduce.mk)             |
| Deterministic hook gates                   | [`hook_gates.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/hook_gates.mk)             |
| Divergent terminals + `fail`               | [`expense_approval.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/expense_approval.mk) |

## Go deeper

- [Patterns](patterns.md) — tier routing, reliability tuning, `mklang test`,
  which architecture when.
- [SPEC](../SPEC.md) — the full semantics; §10 is the pattern cookbook.
- [Schema](../schema/mklang.schema.json) — structural validation for editors.
