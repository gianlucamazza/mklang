# Console

`mklang console` is the agent-first front door: type what you want, the
console's agent picks — or authors — a machine, commissions it, and streams the
run state by state. The agent itself **is** a machine
([`agent.mk`](https://github.com/gianlucamazza/mklang/blob/main/src/mklang/data/console/agent.mk)):
read it, `check` it, `lint --llm` it, scenario-test it, or swap it out entirely.

```bash
pip install 'mklang[console]'
mklang console                 # DeepSeek by default; --provider anthropic|openai|…
```

## Layout

```
┌ mklang console ──────────────────────────────┬─ inspector (F2) ────────┐
│ you: create a machine that triages my CSV    │ [Context|Trace|Session] │
│ agent: created triage_csv.mk and ran it: …   │ …                       │
│ ├ ▶ console_agent                            │                         │
│ │  ● decide [ok] → author                    │                         │
│ │  ● author [ok] → save                      │                         │
│ │  ● save   [ok] → decide                    │                         │
│ │  ● do_run ├ ▶ triage_csv …                 │                         │
├──────────────────────────────────────────────┴─────────────────────────┤
│ session tokens: 922+212 · provider deepseek · 20260717-104512-ab3f     │
│ > _                                                                    │
└────────────────────────────────────────────────────────────────────────┘
```

Conversation on top, the live **activity tree** of the current turn beneath it
(brain states at the top level, each commissioned run nested under the state
that launched it, `call:` sub-runs by depth, fan-out branches as leaves), the
token HUD, and the input line. `F2` toggles the inspector (last run's
blackboard, trace, session facts); `ctrl+l` clears the conversation.

## The agent

One user turn = one run of `agent.mk` (ReAct-shaped): `decide` routes between
**DISCOVER** (list machines), **RUN** (commission one), **CLARIFY** (ask you),
**AUTHOR** (write a new `.mk` into the workspace, validate it, repair on
errors) and **REPLY**. Escalations from a commissioned machine, tool-consent
prompts and turn-budget exhaustion all come back to you through the input line.

Swap the brain with `--agent your_brain.mk` — any machine honoring the same
tool contract (`list_machines`, `describe_machine`, `read_machine`,
`check_machine`, `write_machine`, `run_machine`, `ask_user`).

## Slash commands (bypass the agent)

| command                          | effect                                            |
| -------------------------------- | ------------------------------------------------- |
| `/machines`                      | list commissionable machines with contracts       |
| `/run <name> [k=v…]`             | commission directly (`--set`-style JSON coercion) |
| `/check <name>` / `/read <name>` | validate / show a workspace machine               |
| `/budget <n>`                    | default token budget for commissioned runs        |
| `/resume [n]`                    | list / finish the session's parked turns          |
| `/session`                       | current session facts                             |
| `/help` · `/quit`                | help · exit                                       |

## Sessions

Every conversation persists under `~/.mklang/console/sessions/<id>/`:
`state.json` (history, spend, tool consents — rewritten atomically per turn),
`transcript.jsonl` (turns + every engine event, streaming append), and
`checkpoints/` for turns parked on budget exhaustion. `--continue` reopens the
latest session; `--session <id>` a specific one.

**History for the brain is windowed** (ADR 0017): the full conversation remains
in the session audit / transcript, but only a tail of recent turns (and a char
cap) is injected as `{{history}}` into `agent.mk`, with an explicit
`…[history_truncated…]…` marker when anything is dropped. This keeps long sessions
from exploding the brain prompt.

## Web search from the console

Live web/news questions need a machine with a real `tool: search` state (not
generative prose that pretends to search). Host binding:

| Setup | Effect |
| --- | --- |
| `TAVILY_API_KEY=…` in `.env` | Tavily auto-enabled for the `search` tool |
| `MKLANG_SEARCH_BACKEND=fake` | Deterministic offline hits (demos/tests) |
| `MKLANG_SEARCH_BACKEND=stub` | Force offline even if a Tavily key is set |
| unset key + unset backend | Structured stub: `"no external search bound…"` |

Example workspace machine: `machines/news_search.mk` (topic → search → brief).
Pattern references: `examples/research_web.mk`, `examples/research_compress.mk`.

**Tool consent is not an error.** The first time a machine uses host tools
(`search`, `calc`, …) the console pauses with a yellow prompt and asks you to
allow it for the session. Type **`y`** / **`yes`** / **`sì`** and Enter.
Afterwards it is remembered in the session (inspector: consented tools). Enter
alone means **no**.

## Security model

The console inherits the SPEC §11 posture: authored machines are **confined to
the workspace** (`--workspace`, default `./machines` — path-resolved, no
traversal); running a machine whose states invoke host tools (including
`search` if a machine uses it) asks consent once per tool set (remembered per
session); provider keys stay in the host environment. The console cannot edit
files outside the workspace, run shell commands, or touch git — it is an
operational surface, not an IDE (ADR 0015).

## For other clients

The same live events the console renders are available to every MCP client:
`mklang-mcp`'s `run`/`resume` stream them as `mklang.event` logging
notifications (ADR 0019) — an external front-end needs nothing more.
