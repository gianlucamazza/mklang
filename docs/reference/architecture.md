# Interpreter architecture

How the Python reference interpreter under `src/mklang/` is organized. This is
a contributor's map, not language semantics — those live in the SPEC. The
"change checklist" in CONTRIBUTING says which layers a change must touch.

## Execution pipeline

```
.mkl file ──▶ loader.py ──▶ model.py ──▶ engine.py ──▶ llm/ adapter ──▶ provider
             schema +      dataclasses   run loop:      produce/judge
             semantic      for machine   produce →
             checks        + states      judge gates →
                                         transition
```

- `loader.py` — load and validate a `.mkl`: JSON-Schema (structure, from
  `data/mklang.schema.json`) plus semantic checks.
- `model.py` — dataclasses for a machine and its states, parsed from the plain
  dict post-YAML.
- `engine.py` — the runtime (SPEC §6): the produce → judge-gates → transition
  loop, budgets and termination (SPEC §7), fan-out, `call`, `tool` states, and
  provenance-taint tracking with produce-prompt fencing (SPEC §6, ADR 0025).
  Suspension writes checkpoint frames via `checkpoint.py` (ADR 0007) — frames
  carry the `"tainted"` key set (`taint_frame` marks resume-injected values).
- `interpolate.py` — `{{key.path}}` interpolation and value formatting for
  prompts; `render_delimited` fences tainted substitutions with a per-call
  nonce (ADR 0025).

## LLM layer (`llm/`)

- `base.py` — the interface the engine talks to. Two operations: **produce**
  and **judge** — plus the fixed `JUDGE_SYSTEM` role and the shared
  `build_judge_user` (OUTPUT/REASONING/CONTEXT always fenced, ADR 0025) used
  by both adapters.
- `openai_compat.py` — one adapter for every OpenAI-compatible provider
  (DeepSeek, OpenAI, OpenRouter, xAI, Mistral, local).
- `anthropic.py` — native Anthropic adapter (`mklang[anthropic]` extra).
- `mock.py` — deterministic scripted LLM for tests; no network.
- `prompts.py` — reference-interpreter prompt assembly (host concern, not
  language): sectioned system prompts built from `structure` + `execution`,
  plus the untrusted-data rule when the user message carries a fence.
- `context_view.py` — host-side context rendering budgets (ADR 0017).

## Host surfaces

All surfaces commission runs through the same seam, `host.py`.

- `cli.py` + `presentation.py` — the `mklang` command; typed `CommandResult`s
  rendered as Rich text or stable JSON ([CLI reference](cli.md), ADR 0022).
- `console/` — the TUI (ADR 0015): `app.py` (Textual app), `session.py`
  (crash-tolerant persistence), `commands.py` (slash commands), `render.py`
  (safe conversation rendering), `widgets.py` (activity tree, inspector),
  `tools.py` (the brain machine's hands, including bounded read-only workspace
  listing, search and file reads), `workspace.py` (workspace policy, budgets and
  inspection). The brain itself is a machine:
  `data/console/agent.mkl`.
- `mcp/` — the stdio MCP server (ADR 0011/0013): `server.py` (commissioning +
  provenance, live events per ADR 0019), `sessions.py` (suspended runs keyed by
  opaque handles).

## Extension registries

Plugins hook in via entry-point groups; builtins register the same way.

| Registry       | Entry-point group  | Contract                                     |
| -------------- | ------------------ | -------------------------------------------- |
| `providers.py` | `mklang.providers` | LLM adapter factory                          |
| `tools.py`     | `mklang.tools`     | `(dict) -> str` host tool for `tool:` states |
| `hooks.py`     | `mklang.hooks`     | `(context, output) -> bool` gate hook        |
| `registry.py`  | `mklang.machines`  | directory of `.mkl` machines                  |

## Supporting modules

| Module                                         | Role                                                                                            |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `config.py`                                    | tier→model map per provider; keys from `.env`                                                   |
| `paths.py`                                     | XDG host layout and config/machine discovery (ADR 0021)                                         |
| `errors.py`                                    | typed adapter errors the engine maps to halt reasons                                            |
| `lint.py` / `llmlint.py`                       | static analysis / LLM-assisted lint (ADR 0010)                                                  |
| `scripttest.py`                                | scripted-LLM harness — single source of truth shared by `mklang test` and the conformance suite |
| `search.py`, `kb.py`, `mail.py`, `tool_obs.py` | host tool stubs + shared observation envelope (ADR 0016/0020)                                   |
| `data/stdlib/`                                 | the `std_*` machines ([catalog](stdlib.md), ADR 0012)                                           |
| `data/mklang.schema.json`                      | the JSON Schema `check` validates against                                                       |

## Where to change what

A language change flows SPEC → schema → interpreter → conformance → examples →
tests → docs, in that order — the full checklist is in CONTRIBUTING. A
host-only change (CLI flags, console, MCP) stays in its surface plus
`presentation.py`/`host.py` and needs no SPEC edit.
