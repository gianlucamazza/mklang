# Best practices

Canonical checklist for writing, running, and hosting mklang machines.
**How to author a correct file:** [Authoring](authoring.md).  
**How to tune reliability and cost:** [Patterns](patterns.md).  
**Host tool contracts:** [Tool reference](../reference/tools.md).  
**What the language guarantees:** [SPEC](../../SPEC.md) (cookbook §10, threat model §11).

This page answers: _what should I always do, never do, and where does each rule live?_

---

## 1. Layer discipline (do not mix layers)

| Layer                 | Owns                                                                                                                                  | Examples                                                                                                                         |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Language (`.mkl`)** | Control flow, prose contracts, portable structure                                                                                     | states, gates, tiers, `tool:` _names_, `parse: list`                                                                             |
| **Host runtime**      | Bindings, budgets, clocks, truncation _policy_, LLM adapters, produce/judge prompt assembly, **ops logging**, FS data roots for tools | `tools={…}`, hooks, `on_truncate`, `context.today` / `now` fill, `llm/prompts.py`, process loggers, plugin FS tools              |
| **Surface**           | UX, consent, compact observations, chrome vs content rendering, session audit                                                         | CLI flags, MCP tools, console brain, Markdown log, transcript/session paths, read-only workspace inspection and `.mkl` authoring |

**Rules**

- Side effects live only in **`tool:` states** (host callables). Never in `execution` or generative prompts.
- The `.mkl` **never** names a provider or model — only `tier:` (ADR 0003).
- Host tools are **opaque names** + `(dict) → str`. Do not promote search/bash/FS into language syntax.
- Generic **bash / filesystem** stay **out of core** (console: bounded read-only workspace inspection plus `.mkl` authoring; production I/O = plugins or external host).

---

## 2. Authoring checklist (every machine)

Before shipping a `.mkl`:

- [ ] Schema header + `mklang: "0.4"` when using post-0.2 faces (`parse: list`, `parse: json`, `max_visits`, …).
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
`system:` keyword in the language. Map faces to channels:

| Face / artifact     | LLM channel          | Interpolated?   | Put here                                                                        |
| ------------------- | -------------------- | --------------- | ------------------------------------------------------------------------------- |
| `structure`         | **system** (produce) | No              | Output contract / shape for this state                                          |
| `execution`         | **system** (produce) | No              | Sticky operational policy (never side effects)                                  |
| `prompt`            | **user** (produce)   | **Yes** `{{…}}` | This turn’s task + data — tainted values arrive `<data-NONCE>`-fenced (SPEC §6) |
| `when:` conditions  | judge **user**       | No (prose)      | Gate selection only — stay bare (author-trusted)                                |
| Host `JUDGE_SYSTEM` | judge **system**     | fixed           | Choice protocol `{"choice": n}` — not authorable                                |

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

| Do                                                                             | Don't                                                 |
| ------------------------------------------------------------------------------ | ----------------------------------------------------- |
| Put **hooks above** prose gates; keep `when` as the human-readable trace label | Ask the LLM to check `amount <= 100`                  |
| Cap `repair` at 1–2, then `escalate` or `fail`                                 | Open-ended repair-only states                         |
| Give escalate a **safe sink** state (human / fallback)                         | Fail closed only when that is truly required          |
| Read **trace** (gate, `judge_fallback`, nested `call`) when debugging          | Trust only the final `result` string                  |
| Use `reason: true` when the _why_ must be auditable                            | Dump chain-of-thought into `output` / context         |
| Quote any `when` that contains `#` / `##` (markdown headings)                  | Bare `## Section` in unquoted `when` (YAML truncates) |

**Builtin / parametric hooks** (no plugin): `always_true` / `always_false`,
`write_failed` (write_file observation failed), `eq:key:value` /
`neq:key:value` (string equality on a top-level context key). Put hooks **above**
prose batches so control-flow does not depend on a judge fallback.

Gate judging **follows the state tier** by default. Use config `judge:` only when all gates are deliberately cheap classifications (SPEC §2.1).

Optional: `mklang lint --llm` to probe overlapping prose `when` conditions (advisory; not CI-blocking). `mklang lint` also flags unquoted `#` inside raw `when` lines.

The prose behind each of these rules — and everything else about tuning
reliability — is in [Patterns](patterns.md#reliability-gates-are-the-safety-net).

---

## 5. Tools (host contracts)

Input/output/enable contracts for the reference host tools (`search`,
`search_kb`, `send_reply`, the `list_files`/`read_file`/`write_file` data
tools, `calc`), the ADR 0020 observation envelope, and capability policy are
one page: the [host tool reference](../reference/tools.md). The rules that
belong on this checklist:

- Observations are **untrusted** blackboard data (SPEC §11), fenced
  automatically when interpolated (SPEC §6).
- Side effects only via **`tool:`** states; declare expected tools under
  top-level `tools:`; bind production implementations via entry points
  (`mklang.tools` / `mklang.hooks`).
- A stub `send_reply` is **not** delivery: live means `sent` true **and**
  `stub` false. Never ask the model to confirm a side effect.

---

## 6. Web, time, and knowledge cutoff

Live or news-like questions fail in predictable ways if the machine relies on
model training data:

- **Use `tool: search`** — ready-made as the [`std_research`](../reference/stdlib.md)
  stdlib machine; never “search the web” only in prose.
- **Declare `today: ""`** (and **`now: ""`** for wall-clock) and prompt with
  `Today is {{today}}` / `Current local time is {{now}}` — the host fill
  convention and key table are in [Patterns](patterns.md).
- **Ground finalize in notes only** (titles/URLs/`published_date`); explicitly
  forbid filling gaps from pre-training; when the stub says search is unbound,
  say so — do not fabricate hits.

**Language note:** there is no primitive that “disables knowledge cutoff.”
Discipline is host clock + tools + prose + gates.

---

## 7. Output cutoff and context budgets (anti-cutoff)

- A produce that hits its length stop is marked `truncated: true` in trace and
  events (ADR 0018). Default policy `report` continues with partial text — never
  treat a partial finalize as complete; use `--on-truncate halt` for strict runs.
- Interpolation budgets end long values with `…[truncated]` (ADR 0017);
  compress notes before the next loop (`research_compress.mkl`), and put
  critical facts in **state output**, not only deep context.
- The full tuning detail (`parse: list` halts on truncation, judge CONTEXT
  caps, console observation fields) is in [Patterns](patterns.md).

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

`budget` is steps, `--max-tokens` / `cost_budget` is spend (shared with `call`
children, partitioned across fan-out). Size the step budget to the worst case —
loops, repair headroom, fan-out width — and let `mklang check` reject the
infeasible ones. The sizing rules and the fan-out arithmetic are in
[Patterns](patterns.md); the normative semantics in SPEC §7.

---

## 10. Testing and CI

| Layer              | Command                                   | Role                                  |
| ------------------ | ----------------------------------------- | ------------------------------------- |
| Schema + semantics | `mklang check`                            | Blocking shape/graph                  |
| Static smells      | `mklang lint` (`--strict` in CI)          | Typos, dead gates, missing catch-alls |
| Prose gate overlap | `mklang lint --llm`                       | Advisory only                         |
| Path pinning       | `mklang test … --script …`                | No API keys; escape hatches           |
| Language contract  | `pytest` + `conformance/`                 | Interpreter semantics                 |
| Live smoke         | `MKLANG_LIVE=1 pytest tests/test_live.py` | Opt-in providers                      |

Keep `machine.test.yaml` beside the machine. Cover escalate, repair exhaustion, empty tool results, and search-unbound paths for web machines.

**Static checks are not behavioural correctness.** `check` and `lint` prove a
machine is _well-formed_, not that it _does the right thing_ — only a scenario
run exercises behaviour. This gap matters most for agent-authored machines
(console / MCP, ADR 0015): freeze a hand-written `*.test.yaml` acceptance
scenario before trusting one. Treat “check-clean” as a precondition for
testing, not a substitute.

**Console vs MCP authoring.** The console can `write_machine` into a workspace
(with human overwrite consent); MCP has no persist tool (§11) — headless hosts
author and run inline. The console's authoring turn shares one step budget
across discover/run/author/repair/reply, so prefer tight authoring contracts
over lengthening the loop.

**`escalate` is control-flow-critical.** Prose escalate gates are
non-deterministic under provider and repeats; for production
page/approve/legal paths prefer **`--hitl`** or a **code-hook gate**, and keep
prose escalate for soft routing where an occasional mis-route is acceptable.
`mklang lint` emits an advisory `note:` on machines that use escalate.

---

## 11. Security (SPEC §11) — operational minimum

- Customer text, web snippets, workspace files, and tool observations are
  **injection-capable**: they may be evidence, never new system policy,
  capability grants, budgets, or registry definitions.
- Tainted interpolations and the judge's OUTPUT/REASONING/CONTEXT are
  **automatically fenced** (`<data-NONCE>`, SPEC §6 / ADR 0025). Fencing
  prevents _confusion_, not _persuasion_ — the next bullet still applies.
- **Control-flow taint** (SPEC §6 / ADR 0030): run production paths with
  `--untrusted-flow halt` (equivalents on `run(...)`, MCP, and the console) and
  classify your own tools with `tool_effects=` — an unclassified tool counts as
  effectful. The fix for a finding is a **`hook:` gate or a fresh HITL
  confirmation for that suspension**, not a better prompt; a stale
  `human.reply` in the blackboard does not confirm a later decision.
- Checkpoints hold the **full blackboard in plaintext** (mode `0600` is a
  floor, not encryption) — mind PII retention. No secrets in `.mkl` or
  context; keys stay in host env / `.env`.
- MCP is **read-only to disk by design** — no persist/write tool (ADR
  0011/0013; the only disk write is an explicit per-call `checkpoint_path`).
  The console's interactive guard model does not transfer to headless hosts.
- Production hosts set `MKLANG_ALLOWED_PLUGINS=name1,name2` to allowlist
  entry-point plugins; audit records redact credential-shaped values and never
  contain full prompts or keys at default log levels.
- Console tool **consent** is once per workspace-scoped session; `always yes`
  is an explicit operator choice for low-risk prompts only — high-risk prompts
  (egress, writes, irreversible, unknown tools) are always shown again
  ([console](console.md#security-model)).

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
2. **Ops logging is host-only** — never a face of the `.mkl`, never deposited on
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

| Class                       | Examples                                                                                                                 | Where it lives                            | Controls                                                                                                                                                                                                                                                                                   |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **1. Host-owned paths**     | `runtime.yaml`, checkpoints, console session dir                                                                         | CLI / host config                         | Operator-chosen paths; checkpoint mode `0600`                                                                                                                                                                                                                                              |
| **2. Workspace console**    | `list_workspace` / `read_workspace_file` / `search_workspace` (read-only) plus `write_machine` / `read_machine` (`.mkl`) | Console surface (ADR 0015)                | Root defaults to the launch cwd and is injected as absolute `workspace_root`; `--workspace` overrides it; relative paths; reject escape, hidden/build/vendor/sensitive paths; bounded file/byte budgets; report truncation; confirm `.mkl` overwrite; project machines live in `machines/` |
| **3. Machine data I/O**     | Read CSV, write a report                                                                                                 | Builtins `mklang.fs` (ADR 0024)           | Workspace confinement, size/type limits, write grant, stub off-switch                                                                                                                                                                                                                      |
| **4. Arbitrary FS / shell** | `rm`, bash, git                                                                                                          | **Never core**; explicit sandboxed plugin | Default off; high friction                                                                                                                                                                                                                                                                 |

The current host-owned paths (XDG roots, system layer, config and machine
resolution) are documented once, in [Installation](install.md#host-layout) —
ADR 0021 records the decision history.

### Rules for class 3 (data tools)

Implemented by `mklang.fs` (`list_files` / `read_file` / `write_file` —
contracts in the [tool reference](../reference/tools.md); ADR 0024). The
reference posture is the coding-tool workspace model: reads are live by default
under `--workspace` / `MKLANG_FS_ROOT` / cwd, disk writes need an explicit
grant (`--allow-write` / `MKLANG_FS_WRITE=1` / console consent).

1. **Names only in the `.mkl`** — `tool: read_file`, not path syntax in the language.
2. **Relative paths in tool input**; host joins to the configured **workspace**
   root; `..`, absolute paths, and dotfile segments never resolve.
3. **ADR 0020 envelope** — `{tool, stub, error, …}`; `MKLANG_FS_BACKEND=stub`
   forces the offline refusal tier.
4. **File bodies are untrusted observations** (§11) — never in the produce
   system channel.
5. **No recursive delete / shell in core.** Destructive ops only as explicit
   plugins with strong confirmation.
6. **Audit lightly** — tool name + relative path + byte count at INFO; not
   full file contents.
7. **Console stays non-IDE** — read-only inspection plus `.mkl` authoring;
   no generic write, shell, or git tools.

### Large workspace analysis (ADR 0036)

For large projects, use the console's metadata-only workspace index as the
structural inventory and read file bodies only when they are relevant to the
question. The index is persisted under the user state directory, is rebuilt
incrementally from visible file metadata, and never stores file contents.

- Treat the index as a candidate map, not proof that a file was understood.
- Rank and read relevant files progressively; do not inject an entire tree into
  one prompt.
- Report indexed, read, skipped, and truncated counts in the evidence brief.
- A truncated index or search makes the analysis partial; never call it complete.
- Keep secrets, hidden paths, build/vendor/cache trees, binaries, and databases
  outside both the index and the model context.
- Rebuild or invalidate the index when the canonical workspace root changes or
  the manifest version is incompatible.

### Memory & planning mapping

The class model gives machines the same memory layering native coding agents
use: working memory is the blackboard (`context` + `accumulate`, never on
disk); session state is checkpoints and console `state.json` (class 1, outside
the workspace); project memory (`AGENTS.md`-style files) and plans/reports the
machine produces are non-dotted workspace files (classes 2/3, writes behind
the grant). Host state is unreachable from class-3 tools by construction — the
dotfile ban makes the “session dir as data lake” anti-pattern structural.

### Anti-patterns

- Language face `file:` / `$path` without ADR + conformance.
- `execution: write the result to disk`.
- Widening `write_machine` to arbitrary extensions/paths.
- Using session/transcript directories as a machine “data lake.”
- Absolute paths from the model without canonicalize + root check.

---

## 14. Surfaces quick reference

| Surface             | Best practice                                                                                                                                                                                                                          |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CLI**             | `init` once, `doctor` when in doubt, then `check` → `lint` → `test` → `run`; `--on-truncate halt` for strict research; `--hitl` for human gates (auto-checkpoints; `--checkpoint` to choose the path); ops log on stderr when enabled  |
| **MCP**             | Commission by name/path/source; stream **run** events as `mklang.event` only; durable `checkpoint_path` for multi-process HITL; **read-only to disk** — author/validate/run inline, no persist tool (§11, ADR 0011/0013)               |
| **Library / embed** | Prefer [`host-embedding`](host-embedding.md): `prepare_*` → `run` → `build_output`; map `done`/`suspended`/`halt`; validate against [`run-result.schema.json`](../../schema/run-result.schema.json)                                    |
| **Console**         | Prefer RUN of workspace/search machines for live facts; honor truncation fields; enable Tavily for web; workspace inspection is read-only and `.mkl` authoring is the only write path — the full contract, including cancellation and shutdown, is the [Console guide](console.md) |

---

## 15. Language vs host: what may become language later

Candidates for a future spec revision (need ADR + conformance) — **not** current practice requirements:

| Candidate                             | Why it might become language                                               |
| ------------------------------------- | -------------------------------------------------------------------------- |
| ~~`parse: json`~~                     | **Shipped in 0.4** (ADR 0034) — object-shaped composition is `structure` + gates |
| Machine/state `on_truncate` policy    | Portable anti-cutoff in the document                                       |
| Context zones / pin (ADR 0017 L2)     | Authorable trust zones — runtime provenance taint already ships (ADR 0025) |
| Per-gate `hitl:`                      | Finer HITL than run-level                                                  |
| Budget split (steps vs fan-out width) | Clearer volume caps                                                        |

Until then: use **host policy + patterns + this checklist**. Do **not** invent ad-hoc syntax outside the schema.
