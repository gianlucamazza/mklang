# Best practices

Canonical checklist for writing, running, and hosting mklang machines.
**How to author a correct file:** [Authoring](authoring.md).  
**How to tune reliability and cost:** [Patterns](patterns.md).  
**What the language guarantees:** [SPEC](../../SPEC.md) (cookbook §10, threat model §11).

This page answers: _what should I always do, never do, and where does each rule live?_

---

## 1. Layer discipline (do not mix layers)

| Layer                | Owns                                                                                                                                  | Examples                                                                                                            |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Language (`.mk`)** | Control flow, prose contracts, portable structure                                                                                     | states, gates, tiers, `tool:` _names_, `parse: list`                                                                |
| **Host runtime**     | Bindings, budgets, clocks, truncation _policy_, LLM adapters, produce/judge prompt assembly, **ops logging**, FS data roots for tools | `tools={…}`, hooks, `on_truncate`, `context.today` / `now` fill, `llm/prompts.py`, process loggers, plugin FS tools |
| **Surface**          | UX, consent, compact observations, chrome vs content rendering, session audit                                                         | CLI flags, MCP tools, console brain, Markdown log, transcript/session paths, workspace **`.mk` only**               |

**Rules**

- Side effects live only in **`tool:` states** (host callables). Never in `execution` or generative prompts.
- The `.mk` **never** names a provider or model — only `tier:` (ADR 0003).
- Host tools are **opaque names** + `(dict) → str`. Do not promote search/bash/FS into language syntax.
- Generic **bash / filesystem** stay **out of core** (console: workspace `.mk` only; production I/O = plugins or external host).

---

## 2. Authoring checklist (every machine)

Before shipping a `.mk`:

- [ ] Schema header + `mklang: "0.3"` when using 0.3 faces (`parse: list`, …).
- [ ] Every non-terminal state ends with **`when: otherwise`** (last).
- [ ] At least one path reaches **`END`**; `budget` ≥ shortest path (+ headroom).
- [ ] Every `{{path}}` root is `context:`, a state `output:`, HITL `human.*`, or fan-out `item`/`index`.
- [ ] Exact policy (amounts, allowlists, formats) uses **`hook:`**, not prose alone.
- [ ] Real I/O uses **`tool:`** + top-level `tools:` declarations for documentation.
- [ ] Time-sensitive machines declare **`today: ""`** (and **`now: ""`** for wall-clock) in `context:` and use `Today is {{today}}` / `Current local time is {{now}}` in prompts.
- [ ] Irreversible actions sit behind **`escalate`** (and HITL in production).
- [ ] `mklang check` clean; `mklang lint` clean (use `--strict` in CI).
- [ ] Scenario tests cover happy path **and** escape hatches (`mklang test`).
- [ ] Sticky policy lives in **`execution`** (system channel); turn data and
      `{{…}}` live in **`prompt`** (user channel) — see §3.

---

## 3. Prompt assembly (system vs user)

The reference interpreter builds LLM calls from language faces. There is **no**
`system:` keyword in the language (that would be a 0.4 ADR). Map faces to
channels:

| Face / artifact     | LLM channel          | Interpolated?   | Put here                                                   |
| ------------------- | -------------------- | --------------- | ---------------------------------------------------------- |
| `structure`         | **system** (produce) | No              | Output contract / shape for this state                     |
| `execution`         | **system** (produce) | No              | Sticky operational policy (never side effects)             |
| `prompt`            | **user** (produce)   | **Yes** `{{…}}` | This turn’s task + data — tainted values arrive `<data-NONCE>`-fenced (SPEC §6) |
| `when:` conditions  | judge **user**       | No (prose)      | Gate selection only — stay bare (author-trusted)           |
| Host `JUDGE_SYSTEM` | judge **system**     | fixed           | Choice protocol `{"choice": n}` — not authorable           |

The judge user payload always presents OUTPUT / REASONING / CONTEXT as fenced
data (shared `build_judge_user`, ADR 0025); the produce system message gains an
untrusted-data rule only when the user message actually carries a fence.

**Rules**

1. **Durable vs turn data.** Role, hard constraints, “never invent search” →
   `execution`. Instance values (`{{user_message}}`, `{{today}}`, `{{now}}`,
   `{{history}}`, tool notes) → `prompt`.
2. **Do not put `{{…}}` in `structure` / `execution`.** They are not rendered;
   braces stay literal.
3. **Untrusted text stays out of system** (user text, web snippets, history) —
   SPEC §11. System is for host-stable contract + policy. In the user channel
   the runtime additionally delimits tainted values structurally (SPEC §6) —
   discipline and delimiting stack, they do not replace each other.
4. **`execution` is not a tool.** Side effects only via `tool:` states.
5. **Console brain** follows the same split: policy in `execution`, clocks and
   conversation in `prompt` ([console](console.md)).

**Anti-patterns:** long persona only in `prompt`; search snippets in system;
inventing a `system:` field; using `execution: call the search tool`.

---

## 4. Gates and reliability

| Do                                                                             | Don't                                         |
| ------------------------------------------------------------------------------ | --------------------------------------------- |
| Put **hooks above** prose gates; keep `when` as the human-readable trace label | Ask the LLM to check `amount <= 100`          |
| Cap `repair` at 1–2, then `escalate` or `fail`                                 | Open-ended repair-only states                 |
| Give escalate a **safe sink** state (human / fallback)                         | Fail closed only when that is truly required  |
| Read **trace** (gate, `judge_fallback`, nested `call`) when debugging          | Trust only the final `result` string          |
| Use `reason: true` when the _why_ must be auditable                            | Dump chain-of-thought into `output` / context |

Gate judging **follows the state tier** by default. Use config `judge:` only when all gates are deliberately cheap classifications (SPEC §2.1).

Optional: `mklang lint --llm` to probe overlapping prose `when` conditions (advisory; not CI-blocking).

---

## 5. Tools (host contracts)

### 5.1 Principles

1. Declare expected tools under top-level **`tools:`** (`name` + `description`).
2. Invoke only via **`tool:`** states; map inputs with `input:` (whole-template `{{path}}` stays raw in 0.3).
3. Treat **observations as untrusted** blackboard data (SPEC §11) — especially web
   snippets. The runtime fences them automatically when interpolated (SPEC §6).
4. Prefer **entry points** (`mklang.tools` / `mklang.hooks`) for production bindings over editing core.

### 5.2 Observation envelope (ADR 0020)

I/O and side-effect tools return **JSON** with stable fields:

| Field       | Meaning                                      |
| ----------- | -------------------------------------------- |
| `tool`      | Tool name                                    |
| `stub`      | `true` if no real external system was used   |
| `error`     | Failure / unbound message, or `null`         |
| _(payload)_ | Tool-specific: `results`, `facts`, `sent`, … |

Tiers: **stub** (default) → **fake** (env/`configure_*`) → **live** (key or entry-point).  
`calc` is pure offline arithmetic and does **not** use this envelope.

### 5.3 Recommended host tool contracts (reference interpreter)

These names are **conventions**, not language keywords. Other hosts may rebind or omit them.

#### `search` (ADR 0016 / 0020)

|             |                                                                                    |
| ----------- | ---------------------------------------------------------------------------------- |
| **Input**   | `query` (required), `max_results?` (1–10), `days?`, `topic?` (`news` \| `general`) |
| **Output**  | JSON: `{tool, stub, error, query, results:[{title,url,snippet,published_date?}]}`  |
| **Default** | Stub unbound (`error` explains how to enable)                                      |
| **Enable**  | `TAVILY_API_KEY` (auto), `MKLANG_SEARCH_BACKEND=fake\|tavily\|stub`, or `runtime.yaml` `tools.search.backend` (env wins) |

**Practice:** plan → `tool: search` → check sufficiency → finalize grounded **only** in notes. Never “search the web” only in prose. This exact pattern ships ready-made as the [`std_research`](../reference/stdlib.md) stdlib machine — reach for it before authoring your own.

#### `search_kb` (ADR 0020)

|             |                                                            |
| ----------- | ---------------------------------------------------------- |
| **Input**   | `query` (or `q`)                                           |
| **Output**  | JSON: `{tool, stub, error, query, facts: [str, …], note?}` |
| **Default** | Demo policy facts, always `stub: true`                     |
| **Fake**    | `MKLANG_KB_BACKEND=fake`, `tools.kb.backend: fake`, or `mklang.kb.configure_kb` |

Replace with real RAG via entry points in production.

#### `send_reply` (ADR 0020)

|                  |                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------- |
| **Input**        | `body` (or `draft`), `to?`                                                                          |
| **Output**       | JSON: `{tool, stub, sent, recorded, delivery, to, chars, preview, error, note?}`                    |
| **Default stub** | `sent: false`, `delivery: "stub"` — **does not** claim real mail left the host                      |
| **Fake**         | `MKLANG_MAIL_BACKEND=fake` (or `tools.mail.backend: fake`) → in-memory outbox, `delivery: "fake"`, `sent: true`, still `stub: true` |

Never ask the model to “confirm the message was sent.” Gates should treat `sent: false` as no delivery.

#### `list_files` / `read_file` / `write_file` (ADR 0024)

|             |                                                                                                                                       |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**   | `list_files`: `path?` · `read_file`: `path`, `max_bytes?` · `write_file`: `path`, `content`, `overwrite?`                             |
| **Output**  | JSON: `{tool, stub, error, path, …}` — `entries/count/truncated`, `content/bytes/truncated`, `bytes/written/existed`                  |
| **Default** | **Live reads** confined to the workspace (`MKLANG_FS_ROOT` or cwd); writes refused without a grant                                    |
| **Enable**  | Workspace: `--workspace` / `MKLANG_FS_ROOT` / `tools.fs.workspace` / cwd · Writes: `--allow-write` / `MKLANG_FS_WRITE=1` / `tools.fs.write` · Offline: `MKLANG_FS_BACKEND=stub` or `tools.fs.backend: stub` |

Relative paths only; `..`, absolute paths, and dotfiles are refused; writes are
capped, suffix-allowlisted (never `.mk`), atomic, mode 0600. See §13 for the
class model and rules.

#### `calc`

|            |                                                      |
| ---------- | ---------------------------------------------------- |
| **Input**  | `expr` (or `query`): arithmetic expression           |
| **Output** | Decimal string, or `error: …` (not the I/O envelope) |

Safe subset only (no `eval` of Python). Use for ReAct demos and numeric observations.

### 5.4 What not to bake into the language

| Temptation                              | Keep as                                              |
| --------------------------------------- | ---------------------------------------------------- |
| Web search, HTTP, email, payments       | Host `tool:`                                         |
| Shell / arbitrary FS / git              | Host plugin (sandboxed), never core                  |
| Console `write_machine` / `run_machine` | Console surface only                                 |
| “Current date/time” as `$now` keyword   | Declared `context.today` / `context.now` + host fill |

---

## 6. Web, time, and knowledge cutoff

Live or news-like questions fail in predictable ways if the machine relies on model training data.

| Practice                             | Detail                                                                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Use `tool: search`**               | `std_research` (stdlib, run by name), `research_web.mk`, `research_compress.mk`, `news_search.mk`                                     |
| **Declare `today: ""`**              | Host fills ISO `YYYY-MM-DD` when still empty after inputs (CLI / MCP / console)                                                       |
| **Declare `now: ""` for wall-clock** | Host fills local ISO datetime with offset (e.g. `2026-07-17T14:32:05+02:00`) — use for “what time is it?”, not for news recency alone |
| **Prompt with calendar / clock**     | `Today is {{today}}` / `Current local time is {{now}}`; include year in queries when time-sensitive                                   |
| **Recency inputs**                   | Prefer `days` + `topic: news` for news machines                                                                                       |
| **Ground finalize**                  | Cite titles/URLs/`published_date` from notes only                                                                                     |
| **Forbid fill-in**                   | Explicitly ban inventing facts or answering from pre-training when notes are empty/thin                                               |
| **Honest failures**                  | If stub says search unbound, tell the operator how to enable it — do not fabricate hits                                               |

**Language note:** there is no primitive that “disables knowledge cutoff.” Discipline is host clock + tools + prose + gates.

---

## 7. Output cutoff and context budgets (anti-cutoff)

| Layer                        | What happens                                                                    | Practice                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Produce length stop**      | Trace/events get `truncated: true` (ADR 0018)                                   | Prefer adequate `max_tokens` in runtime `params`; use `--on-truncate halt` for strict runs |
| **Default policy**           | `report` continues with partial text                                            | Do not treat partial finalize as complete without checking trace                           |
| **`parse: list` + truncate** | Halts `parse-list-truncated`                                                    | Keep planner outputs short and well-structured                                             |
| **Produce `{{…}}` budget**   | Long values end with `…[truncated]` (ADR 0017)                                  | Compress notes before the next loop (`research_compress.mk`)                               |
| **Judge CONTEXT**            | Head+tail + `…[context_truncated]…`                                             | Put critical facts in **state output**, not only deep context                              |
| **Console observation**      | Compact JSON: `truncated`, `result_truncated`, `…[truncated]` on clipped result | Brain/user must report cuts — never invent the missing tail                                |

Continue-stitching after length stop is **deferred** (not default).

---

## 8. Memory and composition

| Situation                     | Practice                                                                   |
| ----------------------------- | -------------------------------------------------------------------------- |
| Growing `accumulate` lists    | Explicit **compress** generative state; do not rely on silent host summary |
| Plan → map                    | Planner uses `parse: list`; executor `over: "{{steps}}"`                   |
| Pass lists into `call`/`tool` | Whole-template `input: { x: "{{list}}" }` (0.3 raw resolution)             |
| Reuse architecture            | Prefer **`std_*`** (`call: std_refine`, …) over copy-paste                 |
| Host-dependent patterns       | ReAct / router / hooks stay authored examples, not pure stdlib             |

---

## 9. Budgets and cost

- **Step `budget`:** worst-case path × loops + fan-out width; leave repair headroom.
- **Fan-out:** charges `max(1, len(branches))` at runtime; static check counts fan-out as 1.
- **Token cost:** `--max-tokens` / `cost_budget` shared with `call` children.
- **Tiers:** default `balanced`; cascade `fast` → escalate → `reasoning` for mostly-easy work.
- **Sample diversity:** temperature and/or `{{index}}` in the prompt; do not assume all reasoners sample.

---

## 10. Testing and CI

| Layer              | Command                                   | Role                              |
| ------------------ | ----------------------------------------- | --------------------------------- |
| Schema + semantics | `mklang check`                            | Blocking shape/graph              |
| Static smells      | `mklang lint` (`--strict` in CI)          | Typos, dead gates, unread outputs |
| Prose gate overlap | `mklang lint --llm`                       | Advisory only                     |
| Path pinning       | `mklang test … --script …`                | No API keys; escape hatches       |
| Language contract  | `pytest` + `conformance/`                 | Interpreter semantics             |
| Live smoke         | `MKLANG_LIVE=1 pytest tests/test_live.py` | Opt-in providers                  |

Keep `machine.test.yaml` beside the machine. Cover escalate, repair exhaustion, empty tool results, and search-unbound paths for web machines.

Runs, the console, and `lint --llm` sit behind an upfront provider-key gate:
they fail fast naming the exact `.env` variable to set (`local` is exempt), so
keyless environments stick to `check` / `lint` / `test`.

---

## 11. Security (SPEC §11) — operational minimum

- Treat customer text and search snippets as **injection-capable**.
- Tainted interpolations and the judge's OUTPUT/REASONING/CONTEXT are
  **automatically fenced** (`<data-NONCE>`, SPEC §6 / ADR 0025). Library
  hosts get `run(..., trusted_keys=...)` to vouch for keys and
  `run(..., delimit=False)` for debugging. Fencing prevents *confusion*, not
  *persuasion* — the next two bullets still apply.
- Prefer **hooks + HITL** before irreversible tools.
- Checkpoints hold the **full blackboard** in plaintext (mode `0600` is a floor, not encryption).
- Do not put secrets in `.mk` or context; keys stay in host env / `.env`.
- Console: tool **consent** once per session; workspace confinement for authored `.mk` files.
- Do not confuse **run trace / live events / ops logging** (§12) or turn arbitrary disk into a language feature (§13).

---

## 12. Observability: trace vs events vs process logging

Three channels — do not merge them into one API.

| Channel                   | Purpose                                                        | Consumer                                             | Persistence                                         |
| ------------------------- | -------------------------------------------------------------- | ---------------------------------------------------- | --------------------------------------------------- |
| **Run trace**             | Semantic record: state, gate, policy, tokens, `truncated`      | Authors, tests, checkpoints                          | `RunResult.trace`, checkpoint JSON                  |
| **Live events**           | In-flight progress (`on_event`)                                | Console activity tree; MCP `mklang.event` (ADR 0019) | Ephemeral; console may append to `transcript.jsonl` |
| **Process / ops logging** | Host diagnostics: adapter HTTP, retries, config, plugin errors | Operators, developers                                | stderr / host log file / future OTel                |

### Rules

1. **Trace is the source of truth** for “what the machine did.” Events are a live
   shadow of the same story, not a second semantic model (ADR 0019).
2. **Ops logging is host-only** — never a face of the `.mk`, never deposited on
   the blackboard as “memory,” never a gate condition.
3. **No `tool: log` in core.** Business audit that must be a side effect is a
   named host tool with ADR 0020 envelope + consent — not free-form logging.
4. **Observer isolation.** A failing log sink or event listener must not abort
   the run (same rule as `on_event` / MCP forwarder).
5. **Secrets.** Never log API keys. Prefer no full produce/judge bodies at
   default levels; DEBUG only when explicitly enabled.
6. **Levels.** The host logs on the `mklang.*` hierarchy (`mklang.registry`,
   `mklang.fs`, `mklang.cli`, …) to stderr — `--log-level` or
   `MKLANG_LOG_LEVEL`, default `warning`, format `LEVEL name: message` (no
   timestamps; journald/CI add their own). `DEBUG` adapters/raw HTTP; `INFO`
   coarse host lifecycle (e.g. the fs audit lines); `WARNING` plugin-load
   failures, stub tools, truncation, `judge_fallback`; `ERROR` halts. Do
   **not** INFO-log every state (events already cover that).
7. **Console separation.** Conversation pane ≠ ops log. UI stays Rich/Markdown;
   diagnostics go to stderr or a host log path.
8. **MCP.** Keep `mklang.event` for run vocabulary only. Host stack traces use a
   different logger name (e.g. `mklang.host`), not the event stream.
9. **OTel (optional, later).** Spans are a **projection** of the trace for
   platforms; they do not replace `RunResult.trace` ([ROADMAP](../../ROADMAP.md)).

### Anti-patterns

- `print()` in the engine; log-spam every token at INFO.
- Putting log lines or file tails into context so gates “read the log.”
- Overloading MCP logging notifications with host debug (breaks clients that
  treat `mklang.event` as the run UI feed).

---

## 13. Filesystem: four classes, not one tool

Generic bash/FS stay **out of core**. When you need disk, pick the class:

| Class                       | Examples                                         | Where it lives                            | Controls                                                              |
| --------------------------- | ------------------------------------------------ | ----------------------------------------- | --------------------------------------------------------------------- |
| **1. Host-owned paths**     | `runtime.yaml`, checkpoints, console session dir | CLI / host config                         | Operator-chosen paths; checkpoint mode `0600`                         |
| **2. Workspace authoring**  | `write_machine` / `read_machine` (`.mk` only)    | Console surface (ADR 0015)                | Resolve under workspace; reject escape; confirm overwrite             |
| **3. Machine data I/O**     | Read CSV, write a report                         | Builtins `mklang.fs` (ADR 0024)           | Workspace confinement, size/type limits, write grant, stub off-switch |
| **4. Arbitrary FS / shell** | `rm`, bash, git                                  | **Never core**; explicit sandboxed plugin | Default off; high friction                                            |

### Current host layout (documentation SSOT)

This section is the documentation source of truth for current host-owned paths;
ADR 0021 records the decision and rollout history, while surface guides should
link here instead of maintaining a separate path policy.

| Root   | Current location                                           | Contents                                 |
| ------ | ---------------------------------------------------------- | ---------------------------------------- |
| Config | `$XDG_CONFIG_HOME/mklang` (default `~/.config/mklang`)     | `runtime.yaml`, `.env`                   |
| Data   | `$XDG_DATA_HOME/mklang` (default `~/.local/share/mklang`)  | user `machines/`                         |
| State  | `$XDG_STATE_HOME/mklang` (default `~/.local/state/mklang`) | `console/sessions/<id>/` and checkpoints |
| System | `/etc/mklang`, `/usr/share/mklang/machines`                | system config and machines               |

Console sessions always live under
`$XDG_STATE_HOME/mklang/console/sessions/<id>/`.
`mklang init --user` creates these roots and seeds the user `machines/` with a
commented `hello.mk` sample plus its `hello.test.yaml` scenario (keyless first
run via `mklang test`).
Local vs global (ADR 0023): `runtime.yaml` resolves first-hit-wins
(project → user → `/etc` → bundled) for every entry point, `mklang-mcp`
included; `.env` layers per key — real environment > project `.env` > user
`.env`; `mklang doctor` shows which layer won.
`MKLANG_CONFIG_DIR`, `MKLANG_DATA_DIR`, and `MKLANG_STATE_DIR` override the
corresponding user roots; `MKLANG_CONFIG` selects one runtime config file
directly. The implementation authority is `mklang.paths`; changes to it must
update this table and the console guide in the same commit.

### Rules for class 3 (data tools)

Implemented by `mklang.fs` (`list_files` / `read_file` / `write_file`, §5.3;
ADR 0024). The reference posture is the coding-tool workspace model: reads are
live by default under `--workspace` / `MKLANG_FS_ROOT` / cwd, disk writes need
an explicit grant (`--allow-write` / `MKLANG_FS_WRITE=1` / console consent).

1. **Names only in the `.mk`** — `tool: read_file`, not path syntax in the language.
2. **Relative paths in tool input**; host joins to the configured **workspace**
   root. Refuse path escape after `resolve` (same idea as console
   `_workspace_path`); `..`, absolute paths, and dotfile segments never resolve.
3. **ADR 0020 envelope** — `{tool, stub, error, …}`; `MKLANG_FS_BACKEND=stub`
   forces the offline refusal tier (reads default to live per ADR 0024 — the
   one sanctioned amendment to stub-by-default).
4. **File bodies are untrusted observations** (SPEC §11). Do not put them in the
   produce **system** channel; treat like web snippets (interpolations arrive
   fenced per SPEC §6).
5. **No recursive delete / shell in core.** Destructive ops only as explicit
   plugins with strong confirmation.
6. **Audit lightly** — log tool name + relative path + byte count at INFO; not
   full file contents.
7. **Console stays non-IDE** — do not register general FS tools on the default
   brain; keep workspace **`.mk` only** unless the operator opts into plugins.

### Memory & planning mapping

The class model gives machines the same memory layering native coding agents
use — each level has exactly one home:

| Agent memory level                        | mklang home                                                       | Class |
| ----------------------------------------- | ----------------------------------------------------------------- | ----- |
| Working memory (in-run)                   | Blackboard `context` + `accumulate` (SPEC §4.6) — never on disk   | —     |
| Session state / resume                    | Checkpoints (`0600`) and console `state.json` — outside workspace | 1     |
| Project memory (`AGENTS.md`, `CLAUDE.md`) | Non-dotted files in the workspace, read via `read_file`           | 3     |
| Plans / reports the machine produces      | `write_file` under the workspace, behind the write grant          | 3     |
| Global config / memory hierarchy          | XDG roots + precedence (ADR 0021/0023)                            | 1     |

For machine authors: keep durable machine memory in non-dotted data files in
the workspace (e.g. `memory/notes.md`); update it with read → `write_file`
`overwrite: true`. Host state (checkpoints, sessions) is unreachable from
class-3 tools by construction — the dotfile ban makes the "data lake"
anti-pattern below structural, not just conventional.

### Anti-patterns

- Language face `file:` / `$path` without ADR + conformance.
- `execution: write the result to disk`.
- Widening `write_machine` to arbitrary extensions/paths.
- Using session/transcript directories as a machine “data lake.”
- Absolute paths from the model without canonicalize + root check.

---

## 14. Surfaces quick reference

| Surface     | Best practice                                                                                                                                                                                                                           |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CLI**     | `init` once, `doctor` when in doubt, then `check` → `lint` → `test` → `run`; `--on-truncate halt` for strict research; `--hitl` for human gates (auto-checkpoints; `--checkpoint` to choose the path); ops log on stderr when enabled   |
| **MCP**     | Commission by name/path/source; stream **run** events as `mklang.event` only; durable `checkpoint_path` for multi-process HITL                                                                                                          |
| **Console** | Prefer RUN of workspace/search machines for live facts; honor truncation fields; enable Tavily for web; Markdown chrome/content ([console rendering](console.md#conversation-rendering)); workspace **`.mk` only** — no generic FS/bash |

### Console cancellation and shutdown (documentation SSOT)

- `Ctrl+G` requests cooperative cancellation between states and keeps the
  console open; an active provider response is allowed to finish.
- `Ctrl+C` and `/quit` close the surface. During an active run, shutdown sets
  the cancellation signal, releases pending human input, invokes the optional
  provider `close()` hook to interrupt in-flight I/O, waits for the backing
  worker thread, and then tears down Textual.
- Provider plugins remain compatible without `close()`, but network-backed
  adapters should implement it so console shutdown cannot wait for an SDK
  timeout. Shutdown hooks must be idempotent and must suppress late UI/session
  callbacks after teardown begins.

---

## 15. Anti-patterns (quick list)

1. `execution: use the search tool` on a generative state.
2. Asking the model to confirm a side effect it cannot perform.
3. Prose-only money/policy thresholds.
4. Answering “what happened this week?” without `tool: search` and `today`.
5. Silent acceptance of truncated produce / clipped console result as complete.
6. Unbounded `accumulate` without compress.
7. `budget` sized for the happy path only.
8. Naming `claude-…` / `gpt-…` inside the `.mk`.
9. Putting PII into checkpoints without a retention policy.
10. Expecting stdlib pure machines to perform host I/O.
11. Treating a stub `send_reply` as real delivery (`sent` must be true **and** `stub` false for live).
12. Interpolating user/LLM text into Rich markup in a TUI (`[b]…[/b]`) — use
    Markdown renderables for agent prose and plain/fenced text for everything
    else ([Console](console.md#conversation-rendering)).
13. Putting sticky role/policy only in `prompt` (user) instead of `execution`
    (system), or putting `{{user_message}}` / history into `structure`.
14. Mixing ops logging with run trace/events, or logging secrets/full prompts at
    default levels (§12).
15. Generic filesystem/bash in core, or treating console workspace as full disk
    access (§13).

---

## 16. Language vs host: what may become language later

Candidates for a future **0.4** (need ADR + conformance) — **not** current practice requirements:

| Candidate                             | Why it might become language         |
| ------------------------------------- | ------------------------------------ |
| `parse: json` / object                | Structured composition beyond lists  |
| Machine/state `on_truncate` policy    | Portable anti-cutoff in the document |
| Context zones / pin (ADR 0017 L2)     | Authorable trust zones — runtime provenance taint already ships (ADR 0025) |
| Per-gate `hitl:`                      | Finer HITL than run-level            |
| Budget split (steps vs fan-out width) | Clearer volume caps                  |

Until then: use **host policy + patterns + this checklist**. Do **not** invent ad-hoc syntax outside the schema.

---

## Related

| Doc                                                    | Role                                                         |
| ------------------------------------------------------ | ------------------------------------------------------------ |
| [Getting started](getting-started.md)                  | First-run path: install → init → key → console               |
| [Install](install.md)                                  | pipx / AUR install, host layout, completions                 |
| [Authoring](authoring.md)                              | Recipe + skeleton + faces → LLM channels                     |
| [Patterns](patterns.md)                                | Tiers, reliability, clocks, `execution` usage                |
| [Stdlib](../reference/stdlib.md)                       | Ready `std_*` architectures                                  |
| [Console](console.md)                                  | TUI, rendering, brain clocks, consent, workspace FS          |
| [SPEC §4–§6](../../SPEC.md)                            | Faces + produce/judge semantics, normative §6 delimiting     |
| [SPEC §8](../../SPEC.md)                               | Trace / observability                                        |
| [SPEC §11](../../SPEC.md)                              | Threat model (injection, checkpoints at rest)                |
| [ADR 0015](../adr/0015-console-surface.md)             | Console scope (not an IDE)                                   |
| [ADR 0019](../adr/0019-mcp-live-events.md)             | `mklang.event` vs ops log                                    |
| [ADR 0020](../adr/0020-host-tool-stub-architecture.md) | Tool envelope for I/O (incl. future FS tools)                |
| [ROADMAP](../../ROADMAP.md)                            | OTel maybe; no bash/FS in core                               |
