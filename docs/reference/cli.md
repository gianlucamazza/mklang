# CLI reference

The `mklang` command-line interface, one page. The authoring workflow behind
these commands is in [Authoring](../guides/authoring.md); host layout and
config discovery in [Installation](../guides/install.md).

| Command                 | Purpose                                                                |
| ----------------------- | ---------------------------------------------------------------------- |
| [`run`](#run)           | execute a machine against a provider                                   |
| [`resume`](#resume)     | resume a suspended run from a checkpoint                               |
| [`check`](#check)       | validate machines (schema + semantics)                                 |
| [`lint`](#lint)         | check + static analysis (dead gates, unread outputs, typos)            |
| [`test`](#test)         | run scenario tests against a machine with a scripted LLM (no API keys) |
| [`machines`](#machines) | list commissionable machines (stdlib, plugins) as JSON                 |
| [`init`](#init)         | scaffold project or user config without overwriting files              |
| [`doctor`](#doctor)     | diagnose the resolved setup: config layer, env, keys, machine roots    |
| [`console`](#console)   | agent-first console TUI (bundled in the core install)                  |

## Global conventions

- `mklang --version` prints the package version; bare `mklang` prints a short
  getting-started map (exit 0) instead of a usage error.
- `--format auto|text|json` — `auto` (default) renders a concise Rich view on a
  terminal and keeps stable JSON on piped stdout; `run`, `resume`, and
  `machines` are safe to pipe.
- `--color auto|always|never` — color policy for text output; `NO_COLOR` is
  honored.
- `MKLANG_DEBUG=1` — re-raise unexpected errors with a full traceback instead
  of the one-line diagnostic.
- `--log-level debug|info|warning|error` (or `MKLANG_LOG_LEVEL`; the flag wins) —
  process log level for the `mklang.*` logger hierarchy on stderr
  ([best practices §12](../guides/best-practices.md)). Default `warning`
  keeps today's output; `info` reveals the fs data-tool audit lines.
- A missing provider API key fails fast with a diagnostic naming the exact
  variable to set in `.env` (the `local` provider is exempt); commands that
  never call a provider (`check`, `lint` without `--llm`, `test`, `machines`,
  `init`) are unaffected.
- Shell completions ship as the `[completions]` extra (argcomplete) —
  activation per shell in [Installation](../guides/install.md#shell-completions).

### Exit codes

| Code | Meaning                                                                                       |
| ---- | --------------------------------------------------------------------------------------------- |
| 0    | success (`run` done, `check`/`lint`/`test` pass)                                              |
| 1    | failure: halted run, `check` errors, `lint --strict` findings, `test` mismatch                |
| 2    | usage or host error (bad `--set`, missing extra, unreadable checkpoint)                       |
| 3    | run suspended (budget exhausted with `--checkpoint`, or a fired escalate gate under `--hitl`) |
| 130  | interrupted (Ctrl-C)                                                                          |

### Config resolution and machine precedence

An explicit `--config` wins, followed by `MKLANG_CONFIG`, project config, user
config, system config, and finally the read-only bundled example. Machine names
resolve stdlib → plugins → system → user → project; `mklang machines` shows the
winning source. `.env` layers per key: the real environment wins, then the
project `.env`, then the user host `.env` fills the gaps (ADR 0023). `mklang
doctor` shows which layer won for each surface. Details:
[Installation](../guides/install.md).

## run

```bash
mklang run MACHINE [--set k.path=value]... [options]
```

`MACHINE` is a path or a registered machine name (e.g. `std_cot`).

| Flag                         | Effect                                                                                                     |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `--set k.path=value`         | seed the initial context (repeatable)                                                                      |
| `--config PATH`              | runtime config (auto-discovered when omitted)                                                              |
| `--provider NAME`            | override the config's `active` provider                                                                    |
| `--max-tokens N`             | cost budget: halt once total tokens reach this                                                             |
| `--checkpoint PATH`          | on budget exhaustion suspend and write a resumable checkpoint (plaintext context, written 0600 — SPEC §11; frames record the taint set, SPEC §6) |
| `--hitl`                     | a fired escalate gate suspends for human review (checkpoint defaults to the XDG state root when omitted)   |
| `--strict`                   | refuse to run a document whose `mklang:` version is unsupported (default: warning)                         |
| `--on-truncate report\|halt` | produce truncation policy: annotate the trace (default) or halt with `output-truncated` (ADR 0018)         |

```bash
mklang run examples/self_consistency.mkl \
  --set question.text="What is the capital of Australia?"
```

## resume

```bash
mklang resume CHECKPOINT [--set k.path=value]... [options]
```

| Flag                         | Effect                                                                        |
| ---------------------------- | ----------------------------------------------------------------------------- |
| `--set k.path=value`         | inject values (e.g. the human reply) into the suspended run's context — untrusted by provenance, fenced in prompts (SPEC §6); pre-taint checkpoints resume all-tainted |
| `--config` / `--provider`    | as in `run`                                                                   |
| `--max-tokens N`             | new total budget, including tokens spent before the suspend                   |
| `--hitl`                     | keep suspending on escalate gates even if the checkpoint didn't record it     |
| `--machine PATH`             | machine path override (if the `.mkl` moved)                                    |
| `--checkpoint PATH`          | where to write the checkpoint on re-suspension (default: overwrite the input) |
| `--force`                    | resume even if the machine file changed                                       |
| `--on-truncate report\|halt` | as in `run`                                                                   |

```bash
mklang run examples/expense_approval.mkl --checkpoint ck.json --hitl
mklang resume ck.json --set human.reply="approved, cost center 42"
```

## check

```bash
mklang check MACHINE... [--strict]
```

JSON-Schema validation plus semantic checks (unknown targets, missing entry,
…). `--strict` treats an unsupported `mklang:` version as an error.

## lint

```bash
mklang lint MACHINE... [--strict] [--llm]
```

Everything `check` does, plus advisory static analysis: dead gates, unread
outputs, likely typos.

| Flag                      | Effect                                                                                         |
| ------------------------- | ---------------------------------------------------------------------------------------------- |
| `--strict`                | exit 1 when static findings exist (`--llm` findings stay advisory)                             |
| `--llm`                   | probe prose-gate ambiguity with a live judge (ADR 0010) — costs real tokens, non-deterministic |
| `--llm-samples K`         | synthetic outputs per multi-gate state (default 5)                                             |
| `--llm-repeats R`         | judge repeats per synthetic output (default 3)                                                 |
| `--config` / `--provider` | provider for `--llm`                                                                           |

## test

```bash
mklang test MACHINE --script FILE.test.yaml
```

Runs named scenarios against a **scripted LLM** (produce texts, judge picks)
and scripted tools/hooks — deterministic, no provider or key. Same case format
as the [conformance suite](../../conformance/README.md); a mismatch prints a
minimal diff and exits 1.

```bash
mklang test examples/triage.mkl --script examples/triage.test.yaml
```

## machines

```bash
mklang machines [--dir DIR]
```

Lists commissionable machines (stdlib, plugins; `--dir` adds a project
directory's `.mkl` files) with the winning source per name.

## init

```bash
mklang init [--user] [--dir DIR]
```

Never overwrites existing files. Project mode creates `config/runtime.yaml`,
`config/runtime.schema.json`, `.env`, and `machines/` seeded with a commented
`hello.mkl` sample plus its `hello.test.yaml` scenario script — an immediate,
keyless first run via `mklang test`; `--user` initializes the XDG user host
instead ([Installation](../guides/install.md)).

## doctor

```bash
mklang doctor [--config PATH]
```

Diagnoses the resolved setup without running anything: the winning config file
and layer (project / user / system / bundled), which `.env` files loaded,
per-provider key status (a missing key for the _active_ provider is an error;
`local` is exempt), machine roots with counts, and the state paths. Exit 1 when
the active provider cannot run (ADR 0023).

## console

```bash
mklang console [--workspace DIR] [--agent FILE.mkl] [--continue | --session ID]
```

The agent-first TUI (bundled by default since 0.15.0). `--workspace` confines
machine writes (default: `./machines` when present, else the XDG user machines
dir); `--agent` swaps the console's brain with your own machine;
`--continue`/`--session` reopen sessions. Full guide:
[Console](../guides/console.md).

## mklang-mcp

A separate entry point (`pip install 'mklang[mcp]'`) exposing the same runtime
to MCP hosts: commission a run, stream live events, resume suspended runs. See
[ADR 0011](../adr/0011-mcp-server-surface.md) and the README's MCP section.
