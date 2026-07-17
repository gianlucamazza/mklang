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
(brain states under `▶ console_agent`, each commissioned run nested under the
state that launched it, `call:` sub-runs by depth, fan-out branches as leaves).
State rows are **not** expandable unless they have content: a nested run and/or
an output preview leaf. The token HUD and the input line sit below. `F2`
toggles the inspector (last run's blackboard, trace, session facts); `ctrl+l`
clears the conversation.

## Conversation rendering

The log and activity tree separate **UI chrome** from **untrusted content**
(user text, agent prose, tool observations, event previews) — same discipline as
[best practices](best-practices.md) (surface layer, no Rich-markup interpolation
of model/user text):

| Channel | How it is shown |
| --- | --- |
| Agent reply (`status=done`) | CommonMark via Rich (`**bold**`, lists, fenced code, links) |
| User / HITL answers | Plain text (no Rich markup interpretation) |
| Slash results (`/run`, `/check`) | Fenced `json` (not full-document Markdown) |
| `/read` machine source | Fenced `yaml` |
| Labels (`you:`, `agent:`, errors) | Rich markup **only** for internal chrome strings |
| Activity tree (turn title, machine, state, **output preview**) | Plain `Text` segments with fixed styles — previews are **not** Markdown |

Session history and the JSONL transcript stay **plain text** for audit; only the
display path renders Markdown. Square brackets in model output (`array[0]`,
`[b]…[/b]`) are not treated as Rich tags on either the log or the tree.

## The agent

One user turn = one run of `agent.mk` (ReAct-shaped): `decide` routes between
**DISCOVER** (list machines), **RUN** (commission one), **CLARIFY** (ask you),
**AUTHOR** (write a new `.mk` into the workspace, validate it, repair on
errors) and **REPLY**. Escalations from a commissioned machine, tool-consent
prompts and turn-budget exhaustion all come back to you through the input line.

Swap the brain with `--agent your_brain.mk` — any machine honoring the same
tool contract (`list_machines`, `describe_machine`, `read_machine`,
`check_machine`, `write_machine`, `run_machine`, `ask_user`).

### Brain prompt assembly

Generative states on the brain follow the host mapping
([Best practices §3](best-practices.md)):

| Face | Role for the console agent |
| --- | --- |
| `structure` | Output shape of this step (e.g. one-line DISCOVER/RUN/…, final reply) |
| `execution` | Sticky policy (no fake web search, truncation honesty, clock REPLY rules) |
| `prompt` | Turn data only: `{{today}}` / `{{now}}`, `{{history}}`, `{{user_message}}`, `{{observation}}` |

Wall-clock questions (“che ore sono?”) use host-filled `now` via **REPLY** — the
brain must not AUTHOR a machine solely to read the clock.

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

## Observations from `run_machine` (anti-cutoff honesty)

The brain sees a **compact** JSON observation of each commissioned run, not the
full engine trace. That observation is still honest about cutoff:

| Field | Meaning |
| --- | --- |
| `truncated` | A produce step hit max_tokens/length (ADR 0018) |
| `finish_reason` | Provider stop reason when known |
| `trace` | `{steps, truncated, truncated_steps:[{state, finish_reason?}]}` |
| `result_truncated` | Observation budget clipped a long `result` string |
| `result` | May end with `…[truncated]` when clipped (ADR 0017 style) |

Full events still stream to the activity tree / session transcript. The agent is
instructed not to invent the missing tail of a truncated result, and not to
answer live-web questions from training knowledge alone.

Time-sensitive workspace machines should declare `context.today: ""`; the host
fills today's ISO date before the run (same convention as CLI/MCP). Wall-clock
questions need `context.now: ""` (local ISO datetime). The bundled brain already
declares both — see [Brain prompt assembly](#brain-prompt-assembly).

## Security model

The console inherits the SPEC §11 posture: authored machines are **confined to
the workspace** (`--workspace`, default `./machines` — path-resolved, no
traversal); running a machine whose states invoke host tools (including
`search` if a machine uses it) asks consent once per tool set (remembered per
session); provider keys stay in the host environment. The console cannot edit
files outside the workspace, run shell commands, or touch git — it is an
operational surface, not an IDE (ADR 0015). Generic bash/FS tools stay **out of
core** (optional host plugins only). Full checklist:
[Best practices](best-practices.md).

## For other clients

The same live events the console renders are available to every MCP client:
`mklang-mcp`'s `run`/`resume` stream them as `mklang.event` logging
notifications (ADR 0019) — an external front-end needs nothing more.
