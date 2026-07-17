# Machine stdlib

mklang ships the reasoning architectures of the [cookbook](SPEC.md) as **ready,
general-purpose machines** — parameterized by context, callable from your own
machines, runnable by name. These are ordinary `.mk` documents bundled with the
package (ADR 0012); discover them with `mklang machines` or the MCP
`list_machines` / `describe_machine` tools.

## Using a stdlib machine

By name from the CLI (no file needed):

```bash
mklang run std_self_consistency --set task="Estimate the risk of X"
mklang run std_map_reduce \
  --set task="Summarize the corpus" \
  --set items='["chunk one …", "chunk two …"]' \
  --set item_task="summarize in 2 sentences"
```

From an MCP host: `run(path="std_refine", inputs={"task": "…"})`.

As a subroutine of your own machine — the registry always contains the stdlib:

```yaml
states:
  polish:
    call: std_refine
    input:
      task: "Rewrite this reply: {{draft}}"
      criteria: "courteous, under 150 words, no invented policies"
    output: final
    gates:
      - when: otherwise
        then: ok
        to: END
```

> **Lists cross `call:` as whole-template values** (0.3, SPEC §4.8): an
> `input:` value that is exactly `"{{items}}"` passes the raw list into the
> callee; any mixed template renders to text. From CLI/MCP, list parameters
> (`items`, `personas`) are plain JSON via `--set` / `inputs`.

Your machines always win: a project `.mk` that reuses a `std_*` name shadows
the bundled machine (with a warning). Third-party packages can add machines via
the `mklang.machines` entry-point group.

## Catalog

Uniform contract: input `task` (string), result `answer`.

| machine                | architecture            | flow                                                                 | extra context (defaults)                    | budget | tiers                        |
| ---------------------- | ----------------------- | -------------------------------------------------------------------- | ------------------------------------------- | ------ | ---------------------------- |
| `std_cot`              | Chain-of-Thought        | solve (traced reasoning) → END                                       | —                                           | 3      | balanced                     |
| `std_self_consistency` | Self-consistency        | 5 sampled answers → majority vote → END, or low-confidence flag      | —                                           | 12     | fast → reasoning             |
| `std_refine`           | Reflexion / self-refine | draft → judged vs criteria → repair ×2 → END, or flagged best-effort | `criteria` ("clear, correct, and complete") | 6      | balanced                     |
| `std_tot`              | Tree-of-Thought         | 3 angled proposals → select best → deepen or finalize                | `best` (internal carry, "")                 | 10     | balanced → reasoning         |
| `std_debate`           | Debate / ensemble       | one argument per persona → synthesis with coverage repair            | `personas` (3 generic debaters, list)       | 12     | fast → reasoning             |
| `std_map_reduce`       | Map-Reduce              | apply `item_task` to each item → reduce with `reduce_task`           | `items` (list), `item_task`, `reduce_task`  | 20     | fast → reasoning             |
| `std_cascade`          | Speculative cascade     | fast draft → confident? END : redo at reasoning tier                 | —                                           | 4      | fast → reasoning             |
| `std_plan_execute`     | Plan-and-Execute        | plan (`parse: list`, 0.3) → execute each step → combine              | —                                           | 16     | reasoning → fast → reasoning |

Notes:

- Fan-out widths are fixed (`sample: 5`, `sample: 3`) — `sample`/`over` are
  static by design. `std_map_reduce`/`std_debate` scale with the length of the
  list you pass; keep it within the budget noted in each file.
- Every machine ships a `*.test.yaml` next to it — scripted scenarios you can
  run offline: `mklang test <path>/std_refine.mk --script <path>/std_refine.test.yaml`.
  The test suite pins all of them in CI.

## Not in the stdlib, and why

| pattern            | blocker                                                                                                                                                                                            |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ReAct              | needs host `tool:`s — tool names are static, so the host must author the machine around its own tools ([`examples/react.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/react.mk)) |
| Router-of-experts  | routes to domain `call:` targets, which are static — see [`examples/triage.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/triage.mk)                                              |
| Exact policy gates | needs host `hook:`s — see [`examples/hook_gates.mk`](https://github.com/gianlucamazza/mklang/blob/main/examples/hook_gates.mk)                                                                     |

These stay as documented patterns: the [cookbook](SPEC.md) has the skeletons,
the [authoring guide](authoring.md) the recipe.
