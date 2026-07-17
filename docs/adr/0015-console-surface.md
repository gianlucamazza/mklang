# ADR 0015 — `mklang console`: an agent-first operational TUI whose brain is a machine

Status: Accepted (M1–M3 shipped in package 0.7.0; see `docs/console.md`)

## Context

mklang now has every non-interactive surface: CLI verbs for authors, a library
for embedders, an MCP server for agent hosts, a stdlib of callable
architectures. What it lacks is an **operational front door** — the
claude-code/opencode experience: type what you want in natural language, watch
the work happen live, answer escalations inline, iterate.

Everything such a console needs already exists as a seam: `host.prepare_*` /
`check_machine` / `describe_machine`, the registry with run-by-name, `engine.run`
with suspension/HITL/checkpoints, scripted testing for its own verification.
Two things are missing:

1. **Live execution events.** `engine.run` is a black box until it returns; a
   console must render state-by-state progress while the run is in flight.
2. **The interactive loop itself** — and a decision about what powers it.

The decisive design question is the agent brain. A conventional answer is a
Python tool-calling loop. But mklang's whole thesis is that an agent should be
a **readable, verifiable machine** — a console whose brain is a hidden Python
loop would be the project not believing itself.

## Decision

Add an optional console surface: extra **`mklang[console]`** (Textual),
subcommand **`mklang console`** (guarded import, like the MCP extra), module
`src/mklang/console/`. Three commitments:

### 1. The brain is a bundled `.mk` machine

The console's agent loop is **`agent.mk`** shipped at
`src/mklang/data/console/agent.mk` — a ReAct-shaped machine (understand →
act via `tool:` states → observe/`accumulate` → gate: done | loop), run once
per user turn with the conversation carried in its context. It is **not** in
the stdlib (it depends on console-registered tools) and is **user-swappable**:
`mklang console --agent my_brain.mk` replaces the brain with any machine that
honors the same tool contract. The console's intelligence is a document you
can read, `check`, `lint --llm`, scenario-test, and fork.

The console registers the brain's **host tools** (via `run(tools=...)`, no
entry points):

| tool                                 | effect                                                                                                                                          |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_machines` / `describe_machine` | registry discovery (wraps `host.describe_machine`)                                                                                              |
| `read_machine`                       | source of a machine (bundled or workspace)                                                                                                      |
| `check_machine`                      | `host.check_machine` verbatim — the authoring loop's verifier                                                                                   |
| `write_machine`                      | write a `.mk` **inside the workspace only** (confirm on overwrite)                                                                              |
| `run_machine`                        | commission a machine (name/path/source + inputs JSON + budget); the run's events stream to the UI; suspensions are brokered to the user (below) |
| `ask_user`                           | direct clarification — blocks the machine on a UI reply                                                                                         |

Structured tool inputs ride as JSON strings (tool inputs are rendered strings
by contract); the tools parse them. Nothing here needs a language change —
the brain is an ordinary 0.3 machine.

### 2. Engine event seam (prerequisite, host-visible only)

`engine.run(..., on_event=None)`: an optional callback receiving small dicts —
`state-start`, `state-done` (output preview, gate, policy, to, tokens),
`branch-done` for fan-out and additive `run-finished` (`status` / `error` / usage)
— with `depth` so
nested `call:`/tool-launched runs render as a tree. Purely additive; no
behavior change when absent; the same seam later serves OpenTelemetry export
(ROADMAP). The trace stays the canonical record; events are its live shadow.

### 3. HITL and budgets become UI moments, not failures

- A **target-machine escalation** (`escalate` under HITL) suspends inside
  `run_machine`; the tool brokers the gate's question to the UI, blocks on the
  reply, injects `human.reply`, and resumes — the agent machine just sees the
  tool observation. Implementation: the tool runs on the engine's worker
  thread and awaits a UI future (thread-safe queue into Textual).
- **Per-turn budgets** reuse checkpoints: the brain runs with a step budget and
  optional `cost_budget`; exhaustion suspends, the console shows spend and asks
  "continue?", resuming the same frames. Cost is always visible in the status
  bar (session total, per-turn).
- `write_machine` is confined to the workspace directory; runs of machines
  whose `tool:` states have real side effects surface a consent prompt listing
  the tools before the first execution (SPEC §11 applies to the console too).

### UX shape (Textual)

One conversation pane (user turns, agent narration, live run tree), an input
line with slash commands that bypass the brain for operator use (`/machines`,
`/run <name>`, `/check <path>`, `/resume <ck>`, `/budget`, `/provider`,
`/quit`), and a toggleable inspector (context blackboard, full trace, usage).
Sessions persist under `~/.mklang/console/<id>/` — blackboard, event
transcript (JSONL), checkpoints — and `--continue` reopens the last one.
Headless testing uses Textual's Pilot plus the scripted LLM, so the console
has the same no-key CI story as everything else.

### Milestones (all shipped, 0.7.0)

1. **M1 — seam + skeleton:** `on_event` in the engine; Textual app with brain
   machine, live run tree, HITL broker, cost HUD.
2. **M2 — authoring loop:** `write_machine`/`check_machine` repair cycle,
   workspace, session persistence, `--agent` / `--continue`.
3. **M3 — polish:** slash commands, inspector pane, `/resume` of parked turns,
   activity tree, `agent.mk` scenario tests.

Follow-ups that are **not** console milestones: brain history windowing is
documented under ADR 0017; MCP live events under ADR 0019.

**Package polish (post-M3, no language change):** conversation log renders agent
prose as CommonMark; untrusted text (user, LLM, previews) is never interpolated
into Rich markup tags on the log or activity tree (`console/render.py`). See
`docs/console.md` § Conversation rendering. Slash `/provider` from the UX sketch
above was not shipped — use CLI `--provider` (or a later surface PR).

## Consequences

- mklang gets its front door, and the front door is the thesis: the demo _is_
  a machine, auditable end-to-end (`agent.mk` + trace of every turn).
- The engine gains its first observability seam — needed anyway for OTel — with
  zero semantic change.
- The brain-as-machine bet is real dogfooding: where `agent.mk` proves clumsy
  (authoring long documents, structured decisions), that pressure feeds the
  language (e.g. `parse: json`) instead of being hidden in Python.
- Scope guard: the console is an _operational_ surface, not an IDE — file
  editing beyond the workspace, git, and arbitrary shell stay out.
