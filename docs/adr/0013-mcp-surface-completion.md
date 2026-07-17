# ADR 0013 — MCP surface completion: discovery, check, durable resume

Status: Accepted

## Context

ADR 0011 shipped the commissioning core (`run` + `resume`) and deliberately
deferred three follow-ups, "each behind its own decision": discovery
(`list_machines` / `describe_machine`), validation as structured output
(`check`/`lint`), and cross-process durable resume. Two things changed since:

- The **machine stdlib** (ADR 0012) gives discovery something real to list — an
  MCP host had to learn the `std_*` names from a docstring.
- The in-memory session store dies with the process; a suspended HITL run could
  not be resumed after a server restart, while the CLI's file envelope (0600,
  SPEC §11) already solves persistence.

## Decision

Grow the MCP surface from two tools to five, all above the same host seam:

- **`list_machines`** — the base registry (bundled stdlib + `mklang.machines`
  plugins) as name / source / result / budget / context-keys rows.
  **`describe_machine`** — the full commissionable contract of one machine
  (`host.describe_machine`: entry, budget, tiers, result, context defaults,
  state summary). The CLI gains the symmetric `mklang machines` subcommand
  (JSON, `--dir` adds a project directory's machines).
- **`check`** — validation without running: schema + `semantic_check` + lint
  smells as structured output `{ok, errors, warnings, lint}` via
  `host.check_machine`, which needs **no provider/LLM** (mirroring `mklang
check`/`lint`, which do no tier check either). One tool, not two: lint
  findings ride along instead of duplicating the surface.
- **Durable resume.** `run`/`resume` accept an optional `checkpoint_path`: a
  suspension is then ALSO persisted with the CLI's `save_checkpoint` envelope
  (nothing touches disk otherwise — the ADR 0011 default stands). `resume`
  accepts either an in-memory handle or a checkpoint **file path** — including
  files written by `mklang run --checkpoint` — with `verify_hash` + `force`
  mirroring the CLI. Inline-source machines persist their source text in the
  envelope (new optional `machine_source` key, format still 1) so a
  cross-process resume can rebuild them; re-suspension rewrites the file it
  came from unless redirected.

Run-by-name (ADR 0012) composes: `run(path="std_cot")` needs no filesystem, and
its checkpoints carry a null machine hash (versioned with the package instead).

## Consequences

- An MCP host can now complete the whole loop autonomously: discover what it
  may commission, validate a machine it authored, run it, and survive a server
  restart mid-HITL — without shell access or prior knowledge of the stdlib.
- The surface stays transport: every tool is a thin wrapper over `host.*` or
  the checkpoint envelope, so CLI parity still holds by construction.
- ADR 0011's "never write to disk" default is preserved; persistence is an
  explicit per-call opt-in.
- A CLI resume of an inline-source (MCP) checkpoint fails cleanly — the CLI has
  no `machine_source` path today; teach it only if the need appears.
