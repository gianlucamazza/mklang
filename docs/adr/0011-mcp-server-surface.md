# ADR 0011 — An MCP server surface: machines as commissioned sub-tasks

Status: Proposed

## Context

mklang's thesis is that "the host supplies the interpreter" (README §1): the `.mk` is
the program, some host with an LLM runs it. Two host surfaces exist today. The **CLI**
(`mklang run/resume/check/lint`) is the author's toolchain — the authoring loop. The
importable **library** (`mklang.engine.run`) is the production embedding: a service loads
a machine, supplies tools/hooks/provider, and owns the lifecycle.

A third host class is unserved: **agentic LLM hosts** (Claude Code and other MCP clients).
They cannot embed a Python library — they speak MCP. Today such a host would have to
re-implement the CLI's wiring or shell out to the `mklang` script, neither of which is a
first-class seam.

This matters because a `.mk` is exactly the kind of work an LLM host should *not* do by
free-form reasoning inside its own context: a verifiable finite-state machine with an
explicit `budget`, typed gates, and an auditable `trace`. The disciplined move is for the
host to **commission** the machine and receive a result *with provenance* — the same
inversion this project already commits to for reasoning (ADR 0005, reasoning first-class):
the host does not *execute* the machine, it *requests* it and gets back a `RunResult`
carrying `trace` + `usage`. MCP is the missing transport for that request.

Neither the ROADMAP nor SPEC reserved an MCP surface before this decision — a new
direction that opens as design, not as code. (Numbered **0011** because **0010** is
already taken by LLM-assisted lint.)

## Decision

Add an **optional MCP stdio server** as a new, non-default host surface. Ship it as an
in-repo extra, not a separate package: module `src/mklang/mcp/`, dependency group
`mklang[mcp]`, console script `mklang-mcp`. Built on the official MCP Python SDK (the
`mcp` package — FastMCP + stdio transport); the exact version is pinned by the
implementation change, not this ADR.

- **Reuse the CLI seams, do not fork logic.** The server calls the same
  `_prepare` (`cli.py`) — provider/LLM/registry/machine load plus `semantic_check` +
  `check_tiers` — and returns the same object `_emit` builds:
  `{status, error, result, usage, trace, at?}`. Parity with the CLI is by construction;
  there is no second interpreter path to drift. The language stays 0.2; the schema is
  untouched.

- **Tool `run`.** Accepts the machine as an **inline `.mk` source string OR a filesystem
  path**; `inputs` (a dict merged onto `machine.context`, the wire form of `--set`);
  optional `cost_budget`, provider/config selection, and `hitl` flag. Returns the `_emit`
  shape as MCP **structured output** — `trace` passes through as nested JSON unchanged.
  - *Inline source has no parent directory*, so the server **builds the `registry` in
    memory** from the single supplied machine. A `call:` to a target that was not supplied
    surfaces cleanly as a `semantic_check` error (the same error the CLI would raise), not
    a crash. Path-loaded machines keep parent-directory sibling discovery
    (`load_registry`), exactly as the CLI does.

- **Tool `resume`.** Takes an **opaque checkpoint handle** (not a file path), optional
  injected values (the HITL reply, e.g. `human.reply`, written into the innermost frame's
  context per ADR 0008), and an optional new budget. Returns the same `_emit` shape.
  - *Deliberate divergence from the CLI's checkpoint model.* The CLI writes a `0600`
    plaintext checkpoint file holding the full blackboard (SPEC §11, checkpoint at rest).
  A remote MCP host
    should not touch the server's filesystem, so on suspension the `run` tool returns
    `status: "suspended"` plus an **opaque handle** and holds the `frames` in a
    process-scoped **in-memory session store** — never written to disk unless explicitly
    requested. The file envelope (`save_checkpoint`/`load_checkpoint`) remains the
    persistence fallback; cross-process durability is a later extension.

- **Above the interpreter, not a new semantics.** The MCP server is just another host
  sitting *above* `engine.run`. It introduces no new authority and no logic the CLI and
  library do not already have — it is transport. Provider API keys resolve **server-side
  from the environment** (as in `_prepare`), never over the wire. Implementation may
  promote `_prepare`/`_emit` (or thin public wrappers) so the MCP module does not
  import private CLI symbols — that is a packaging detail, not a design fork.

- **Minimal surface, on purpose.** The initial surface is exactly `run` + `resume` — the
  commissioning core. `check`/`lint` (validation as structured output) and
  `list_machines`/`describe_machine` (Action-Space-style discovery, so a host can learn
  what it may commission) are natural follow-ups, each behind its own decision, and are
  **not** included here.

## Consequences

- Any MCP-capable agent host can commission an mklang machine — inline or by path — and
  receive a result with full provenance (`trace` + `usage`), realizing the
  "commission, don't execute" inversion for an external host.
- Parity with the CLI is guaranteed by reusing `_prepare`/`_emit`; the MCP surface cannot
  drift from the reference interpreter's semantics.
- The surface stays small (`run` + `resume`), keeping the initial blast radius minimal and
  leaving validation/discovery to later, separately-decided tools.
- The opaque in-memory checkpoint handle intentionally diverges from the CLI's on-disk
  file model — a host-appropriate choice that keeps the full plaintext context off the
  server's disk by default (SPEC §11, checkpoint at rest). Durable, cross-process resume
  is deferred.
- A new optional dependency only; the core install is unaffected and remains fully offline
  with no MCP present.
