# Console

`mklang console` is the agent-first front door: type what you want, the
console's agent picks — or authors — a machine, commissions it, and streams the
run state by state. The agent itself **is** a machine
([`agent.mkl`](https://github.com/gianlucamazza/mklang/blob/main/src/mklang/data/console/agent.mkl)):
read it, `check` it, `lint --llm` it, scenario-test it, or swap it out entirely.

```bash
pip install mklang  # the console ships by default since 0.15.0
mklang console                 # DeepSeek by default; --provider anthropic|openai|…
```

## Layout

```
┌ mklang console ──────────────────────────────┬─ inspector (F2) ────────┐
│ READY · deepseek · tokens 922+212 · session …│                         │
│ you: create a machine that triages my CSV    │ [Context|Trace|Session] │
│ agent: created triage_csv.mkl and ran it: …   │ …                       │
│ ▼ console_agent                              │                         │
│ │  ● decide [ok] → author                    │                         │
│ │  ● author [ok] → save                      │                         │
│ │  ● save   [ok] → decide                    │                         │
│ │  ● do_run ┬ ▼ triage_csv …                 │                         │
├──────────────────────────────────────────────┴─────────────────────────┤
│ > _                                                                    │
└────────────────────────────────────────────────────────────────────────┘
```

Conversation is the primary workspace, with the bounded live **activity tree**
of the current turn beneath it
(brain states under `console_agent`; Textual draws a single expand toggle ▶/▼
per expandable row — run labels are the machine name only). Each commissioned
run nests under the state that launched it; `call:` sub-runs by depth; fan-out
branches as leaves. The status strip reports provider, session token spend, and
current phase; `READY`, `RUNNING`, `WAITING`, `STOPPING`, and `ERROR` are
distinct operator states.
Normal state output stays in the inspector; only exceptional/truncated previews
expand the tree. `F2` toggles the inspector (docked at 100+ columns, full workspace
below that), `ctrl+t` toggles activity, `ctrl+g` requests a cooperative stop after
the current state, and `ctrl+l` clears the conversation.

The shell uses semantic operator states rather than color alone: `● READY`,
`◐ RUNNING`, `⏸ WAITING`, `■ STOPPING`, and `! ERROR`. The input border changes
to an amber answer mode for consent, HITL, and budget questions; disabled input
means the worker is still active. The inspector starts with explicit empty
states, then exposes the latest context, trace, and session facts. On narrow
terminals `F2` changes the inspector from a docked panel into the full workspace.

## Conversation rendering

The log and activity tree separate **UI chrome** from **untrusted content**
(user text, agent prose, tool observations, event previews) — same discipline as
[best practices](best-practices.md) (surface layer, no Rich-markup interpolation
of model/user text):

| Channel                                                        | How it is shown                                                         |
| -------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Agent reply (`status=done`)                                    | CommonMark via Rich (`**bold**`, lists, fenced code, links)             |
| User / HITL answers                                            | Plain text (no Rich markup interpretation)                              |
| Slash results (`/run`, `/check`)                               | Fenced `json` (not full-document Markdown)                              |
| `/read` machine source                                         | Fenced `yaml`                                                           |
| Labels (`you:`, `agent:`, errors)                              | Rich markup **only** for internal chrome strings                        |
| Activity tree (turn title, machine, state, **output preview**) | Plain `Text` segments with fixed styles — previews are **not** Markdown |

Session history and the JSONL transcript stay **plain text** for audit; only the
display path renders Markdown. Square brackets in model output (`array[0]`,
`[b]…[/b]`) are not treated as Rich tags on either the log or the tree.

## The agent

One user turn = one run of `agent.mkl` (ReAct-shaped): `decide` routes between
**WORKSPACE_SCAN / SEARCH / READ / ANALYZE** (read-only project inspection),
**DISCOVER** (list machines), **RUN** (commission one), **CLARIFY** (ask you),
**AUTHOR** (write a new `.mkl` into the workspace, validate it, repair on
errors) and **REPLY**. A project-analysis request must inspect the workspace
before replying; the final answer is expected to distinguish observed facts,
inferences and uninspected areas. Escalations from a commissioned machine,
tool-consent prompts and turn-budget exhaustion all come back to you through the
input line.

The default brain can use `list_workspace`, `read_workspace_file` and
`search_workspace` for visible UTF-8 project files. Reads are relative to the
configured workspace and exclude hidden, build, vendor and cache directories;
they never grant shell or write access. Each operation is bounded (400 listing
entries, 120,000 bytes per read, 80 search matches, 2,000 files and 64 MiB per
search), skips obvious credentials/keys/databases, and reports truncation or
skipped content. Explicit project-analysis turns are host-guarded: the brain
cannot finish until workspace evidence and an evidence brief exist. Swap the
brain with `--agent your_brain.mkl` — custom brains
that want project inspection should declare and use the same workspace tools in
addition to the existing contract (`list_machines`, `describe_machine`,
`read_machine`, `check_machine`, `write_machine`, `run_machine`, `ask_user`).

Tool consent is scoped to the commissioned machine and tool (`machine:tool`),
not only to a global tool name. Machine discovery exposes conservative risk
metadata (`read_only`, `external_egress`, `irreversible`, `sensitivity`,
`idempotent`); these are host policy hints and cannot be self-granted by the
brain.

### Brain prompt assembly

Generative states on the brain follow the host mapping
([Best practices §3](best-practices.md)):

| Face        | Role for the console agent                                                                    |
| ----------- | --------------------------------------------------------------------------------------------- |
| `structure` | Output shape of this step (e.g. one-line DISCOVER/RUN/…, final reply)                         |
| `execution` | Sticky policy (no fake web search, truncation honesty, clock REPLY rules)                     |
| `prompt`    | Turn data only: `{{today}}` / `{{now}}`, `{{history}}`, `{{user_message}}`, `{{workspace_context}}`, `{{workspace_brief}}`, `{{observation}}` |

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

`Ctrl+C` performs a clean shutdown: an active run is cancelled, any pending
human prompt is released, and the console waits for the provider worker to stop
before returning to the shell. `Ctrl+G` only requests cancellation of the
current run and keeps the console open. The lifecycle contract is maintained in
[Best practices §14](best-practices.md#console-cancellation-and-shutdown-documentation-ssot).

Slash commands use shell-style quoting, so `/run demo task="hello world"` keeps
the value together. Every `/run` argument must be `key=value`; malformed
arguments are rejected before the worker starts. Command names are suggested
while typing, and `/help` includes copyable examples.

## Sessions

Every conversation persists under
`$XDG_STATE_HOME/mklang/console/sessions/<id>/` (default
`~/.local/state/mklang/console/sessions/<id>/`):
`state.json` (history, spend, tool consents, and the session's `always yes`
choice — rewritten atomically per turn),
`transcript.jsonl` (turns + every engine event, streaming append), and
`checkpoints/` for turns parked on budget exhaustion. `--continue` reopens the
latest session and replays recoverable user, agent, and slash-result records into
the conversation pane; a torn final transcript line is ignored. Unexpected
worker errors are shown as actionable `ERROR` state and re-enable the prompt.
`--session <id>` reopens a specific one. The canonical host layout is
maintained in
[Best practices §13](best-practices.md#current-host-layout-documentation-ssot).

**History for the brain is windowed** (ADR 0017): the full conversation remains
in the session audit / transcript, but only a tail of recent turns (and a char
cap) is injected as `{{history}}` into `agent.mkl`, with an explicit
`…[history_truncated…]…` marker when anything is dropped. This keeps long sessions
from exploding the brain prompt.

## Web search from the console

Live web/news questions need a machine with a real `tool: search` state (not
generative prose that pretends to search). Host binding:

| Setup                        | Effect                                         |
| ---------------------------- | ---------------------------------------------- |
| `TAVILY_API_KEY=…` in `.env` | Tavily auto-enabled for the `search` tool      |
| `MKLANG_SEARCH_BACKEND=fake` | Deterministic offline hits (demos/tests)       |
| `MKLANG_SEARCH_BACKEND=stub` | Force offline even if a Tavily key is set      |
| unset key + unset backend    | Structured stub: `"no external search bound…"` |

Example workspace machine: `machines/news_search.mkl` (topic → search → brief).
The stdlib `std_research` (search → ground) is always runnable by name.
Pattern references: `examples/research_web.mkl`, `examples/research_compress.mkl`.

**Tool consent is not an error.** The first time a machine uses host tools
(`search`, `calc`, …) the console pauses with a yellow prompt and asks you to
allow it for the session. Type **`y`** / **`yes`** / **`sì`** and Enter.
Type **`always yes`** to approve this and future low-risk confirmation prompts
in the session, including budget-continuation prompts. High-risk prompts for
external egress, writes, irreversible actions, or unknown third-party tools are
always shown again. The choice is
persisted when the session is reopened with `--continue` or `--session`.
Afterwards tool consent is remembered in the session (inspector: consented
tools). Enter alone means **no**.

## Observations from `run_machine` (anti-cutoff honesty)

The brain sees a **compact** JSON observation of each commissioned run, not the
full engine trace. That observation is still honest about cutoff:

| Field              | Meaning                                                         |
| ------------------ | --------------------------------------------------------------- |
| `truncated`        | A produce step hit max_tokens/length (ADR 0018)                 |
| `finish_reason`    | Provider stop reason when known                                 |
| `trace`            | `{steps, truncated, truncated_steps:[{state, finish_reason?}]}` |
| `result_truncated` | Observation budget clipped a long `result` string               |
| `result`           | May end with `…[truncated]` when clipped (ADR 0017 style)       |

Full events still stream to the activity tree / session transcript. The agent is
instructed not to invent the missing tail of a truncated result, and not to
answer live-web questions from training knowledge alone.

Search observations are also bounded before they are accumulated into a
machine's working notes: titles are capped at 300 characters, URLs at 500, and
snippets at 800. A field shortened at that boundary ends with
`…[truncated]`. This keeps a second search batch from displacing the first
batch from the prompt while preserving the JSON envelope and the cutoff signal.
For larger research loops, use the `research_compress` pattern to rewrite notes
between searches.

Time-sensitive workspace machines should declare `context.today: ""`; the host
fills today's ISO date before the run (same convention as CLI/MCP). Wall-clock
questions need `context.now: ""` (local ISO datetime). The bundled brain already
declares both — see [Brain prompt assembly](#brain-prompt-assembly).

## Security model

The console inherits the SPEC §11 posture: authored machines and read-only
project inspection are **confined to the workspace** (`--workspace`, or the
absolute directory from which the console was launched by default — path-resolved,
no traversal); the selected root is injected into the brain as `workspace_root`.
The snapshot and every workspace-tool result repeat that absolute root, while
file arguments remain relative and confined to it.
Global and user machines remain available through discovery but do not change this
inspection root. Running a machine whose states invoke host tools (including
`search` if a machine uses it) asks consent once per tool set (remembered per
session); provider keys stay in the host environment. The console cannot edit
files outside the workspace, run shell commands, or touch git — it is an
operational surface, not an IDE (ADR 0015). Workspace FS is **class 2**:
read-only inspection plus `.mkl` authoring; generic data FS / bash are **out of core** (host plugins only —
[Best practices §13](best-practices.md)). Session `transcript.jsonl` is surface
audit, not a substitute for host ops logging ([§12](best-practices.md)).

## For other clients

The same live events the console renders are available to every MCP client:
`mklang-mcp`'s `run`/`resume` stream them as `mklang.event` logging
notifications (ADR 0019) — an external front-end needs nothing more.
