# Language cheatsheet

The whole language on one page. Normative text: [SPEC](../../SPEC.md) (section
references below); the how-to recipe is [Authoring](../guides/authoring.md).

## Minimal machine

```yaml
mklang: "0.3" # spec version (optional; recommended)
machine: answer
entry: draft
budget: 6 # max steps per run (anti-loop guard)
states:
  draft:
    structure: A short factual answer.
    prompt: "Answer the question: {{question.text}}"
    output: answer
    gates:
      - when: the answer addresses the question
        then: ok
        to: END
      - when: otherwise
        repair: 2
        to: draft
```

## Top-level keys (SPEC §3)

| Key               | Meaning                                                     |
| ----------------- | ----------------------------------------------------------- |
| `machine`         | machine identifier                                          |
| `entry`           | entry state id                                              |
| `budget`          | max steps per run (SPEC §7)                                 |
| `default_tier`    | `fast\|balanced\|reasoning`; default `balanced` (SPEC §2.1) |
| `result`          | context key returned to a caller; default = last output     |
| `context`         | initial blackboard values                                   |
| `tools` / `hooks` | document host tools and gate hooks the machine expects      |
| `states`          | map of state id → state definition                          |

## The four core faces (SPEC §4)

| Face        | Role                                                  |
| ----------- | ----------------------------------------------------- |
| `structure` | **what shape** — the I/O contract, prose              |
| `prompt`    | **what to think** — the task, `{{…}}`-interpolatable  |
| `execution` | **how to act** — operational policy, prose (optional) |
| `gates`     | **when to exit** — post-conditions + transitions      |

## Optional faces

A state is exactly one of generative (`prompt`), call (`call`), or tool
(`tool`); `sample` and `over` are mutually exclusive.

| Face               | Effect (SPEC §)                                               |
| ------------------ | ------------------------------------------------------------- |
| `tier`             | per-state tier override — `fast\|balanced\|reasoning` (§2.1)  |
| `reason`           | private chain-of-thought, traced (§4.5)                       |
| `accumulate`       | append to a list under `output` instead of overwriting (§4.6) |
| `sample: N`        | fan-out: run N times → output is a list (§4.7)                |
| `over: "{{list}}"` | fan-out: run once per item → output is a list (§4.7)          |
| `call`             | run another machine as a subroutine (§4.8)                    |
| `tool`             | run a host-registered callable (§4.9)                         |
| `input`            | map parent context → sub-machine/tool input (§4.8–4.9)        |
| `parse: list`      | deposit a parsed JSON array instead of text (§4.10)           |
| `output`           | context key where the state's result lands                    |

## Gates (SPEC §5)

Evaluated top to bottom, first true wins. Every non-terminal state should end
with `when: otherwise`; if no gate matches, the run halts (`no-gate-matched`).

```yaml
gates:
  - when: <condition, prose or label> # judged by the LLM unless hook/otherwise
    hook: <name> # optional: host predicate (context, output) -> bool — no LLM
    then: ok # …or repair: N / escalate: true / fail: true
    to: <state-id|END> # omitted only for fail
```

| Policy      | Effect                                                                         |
| ----------- | ------------------------------------------------------------------------------ |
| `then: ok`  | transition to `to`                                                             |
| `repair: N` | re-run with the failed `when` injected as feedback; at most N repairs (§5, §7) |
| `escalate`  | route to a handler state — with `--hitl`, suspends for a human (ADR 0008)      |
| `fail`      | abort the run                                                                  |

## Interpolation

`{{key.path}}` reads the context blackboard (SPEC §3). Machine-declared empty
`today` / `now` keys MAY be filled by the host with the ISO date / timestamp
(SPEC §6) — declare them instead of asking the model for the date.

## Tiers (SPEC §2.1)

`fast` | `balanced` | `reasoning` — capability tiers, never provider or model
names. The runtime config maps each tier to a concrete model; a state's tier
applies to both its generation and its gate judging.

## Run it

```bash
mklang check machine.mk && mklang run machine.mk --set question.text="…"
```

All commands and flags: [CLI reference](cli.md).
