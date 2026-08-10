# Host tool contracts

The reference interpreter's built-in host tools, one page: principles, the
shared observation envelope, and the per-tool input/output/enable contracts.
These names are **conventions**, not language keywords — other hosts may rebind
or omit them. Operational do/don't: [Best practices](../guides/best-practices.md);
the language side of `tool:` states is [SPEC §4.9](../../SPEC.md).

## Principles

1. Declare expected tools under top-level **`tools:`** (`name` + `description`).
2. Invoke only via **`tool:`** states; map inputs with `input:` (whole-template
   `{{path}}` stays raw in 0.3).
3. Treat **observations as untrusted** blackboard data (SPEC §11) — especially web
   snippets. The runtime fences them automatically when interpolated (SPEC §6).
4. Prefer **entry points** (`mklang.tools` / `mklang.hooks`) for production bindings over editing core.

## Observation envelope (ADR 0020)

I/O and side-effect tools return **JSON** with stable fields:

| Field       | Meaning                                      |
| ----------- | -------------------------------------------- |
| `tool`      | Tool name                                    |
| `stub`      | `true` if no real external system was used   |
| `error`     | Failure / unbound message, or `null`         |
| `status`    | `ok` or `error`                              |
| `retryable` | Whether the host may safely retry            |
| `untrusted` | Observation is data, never policy            |
| _(payload)_ | Tool-specific: `results`, `facts`, `sent`, … |

Tiers: **stub** (default) → **fake** (env/`configure_*`) → **live** (key or entry-point).  
`calc` is pure offline arithmetic and does **not** use this envelope.

## `search` (ADR 0016 / 0020)

|             |                                                                                                                          |
| ----------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Input**   | `query` (required), `max_results?` (1–10), `days?`, `topic?` (`news` \| `general`)                                       |
| **Output**  | JSON: `{tool, stub, error, query, results:[{title,url,snippet,published_date?}]}`                                        |
| **Default** | Stub unbound (`error` explains how to enable)                                                                            |
| **Enable**  | `TAVILY_API_KEY` (auto), `MKLANG_SEARCH_BACKEND=fake\|tavily\|stub`, or `runtime.yaml` `tools.search.backend` (env wins) |

**Practice:** plan → `tool: search` → check sufficiency → finalize grounded **only** in notes. Never “search the web” only in prose. This exact pattern ships ready-made as the [`std_research`](stdlib.md) stdlib machine — reach for it before authoring your own.

## `search_kb` (ADR 0020)

|             |                                                                                 |
| ----------- | ------------------------------------------------------------------------------- |
| **Input**   | `query` (or `q`)                                                                |
| **Output**  | JSON: `{tool, stub, error, query, facts: [str, …], note?}`                      |
| **Default** | Demo policy facts, always `stub: true`                                          |
| **Fake**    | `MKLANG_KB_BACKEND=fake`, `tools.kb.backend: fake`, or `mklang.kb.configure_kb` |

Replace with real RAG via entry points in production.

## `send_reply` (ADR 0020)

|                  |                                                                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Input**        | `body` (or `draft`), `to?`                                                                                                          |
| **Output**       | JSON: `{tool, stub, sent, recorded, delivery, to, chars, preview, error, note?}`                                                    |
| **Default stub** | `sent: false`, `delivery: "stub"` — **does not** claim real mail left the host                                                      |
| **Fake**         | `MKLANG_MAIL_BACKEND=fake` (or `tools.mail.backend: fake`) → in-memory outbox, `delivery: "fake"`, `sent: true`, still `stub: true` |

Never ask the model to “confirm the message was sent.” Gates should treat
`sent: false` as no delivery — live means `sent` true **and** `stub` false.

## `list_files` / `read_file` / `write_file` (ADR 0024)

|             |                                                                                                                                                                                                             |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**   | `list_files`: `path?` · `read_file`: `path`, `max_bytes?` · `write_file`: `path`, `content`, `overwrite?`                                                                                                   |
| **Output**  | JSON: `{tool, stub, error, path, …}` — `entries/count/truncated`, `content/bytes/truncated`, `bytes/written/existed`                                                                                        |
| **Default** | **Live reads** confined to the selected workspace (`--workspace` for console/MCP, otherwise `MKLANG_FS_ROOT` or cwd); writes refused without a grant                                                        |
| **Enable**  | Workspace: `--workspace` / `MKLANG_FS_ROOT` / `tools.fs.workspace` / cwd · Writes: `--allow-write` / `MKLANG_FS_WRITE=1` / `tools.fs.write` · Offline: `MKLANG_FS_BACKEND=stub` or `tools.fs.backend: stub` |

Relative paths only; `..`, absolute paths, and dotfiles are refused; writes are
capped, suffix-allowlisted (never `.mkl`), atomic, mode 0600. The class model
and rules these tools implement:
[Best practices §13](../guides/best-practices.md).

## `calc`

|            |                                                      |
| ---------- | ---------------------------------------------------- |
| **Input**  | `expr` (or `query`): arithmetic expression           |
| **Output** | Decimal string, or `error: …` (not the I/O envelope) |

Safe subset only (no `eval` of Python). Use for ReAct demos and numeric observations.

## What not to bake into the language

| Temptation                              | Keep as                                              |
| --------------------------------------- | ---------------------------------------------------- |
| Web search, HTTP, email, payments       | Host `tool:`                                         |
| Shell / arbitrary FS / git              | Host plugin (sandboxed), never core                  |
| Console `write_machine` / `run_machine` | Console surface only                                 |
| “Current date/time” as `$now` keyword   | Declared `context.today` / `context.now` + host fill |

## Capability policy

A machine may request a tool, but only the host grants a capability. Interactive
grants should be scoped at least by `machine:tool`; production side effects
should additionally scope operation, path, quantity, duration, and
reversibility. Unknown third-party tools default to conservative high-risk
metadata (`external_egress`, `irreversible`, `sensitivity=unknown`).

The console records scoped grants such as `machine:tool` and exposes conservative
risk metadata during discovery. A machine cannot grant itself a capability, and
a consent prompt must not be treated as a replacement for host policy.
