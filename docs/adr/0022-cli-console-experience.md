# ADR 0022 — Human-first CLI presentation and responsive console workspace

Status: Accepted

## Context

The CLI mixed parsing, execution, and printing, while the Textual console used a
fixed three-pane layout. Direct terminal use exposed large JSON documents, narrow
terminals clipped session data, expected errors could escape as tracebacks, and
the activity stream had no terminal run event.

## Decision

1. Rich is a core dependency. Commands return typed presentation results and the
   shared presenter renders text or JSON. `--format auto|text|json` and
   `--color auto|always|never` are common surface controls.
2. Auto mode preserves automation contracts: `run`, `resume`, and `machines`
   retain their existing JSON on non-TTY stdout; validation/test commands retain
   plain text unless JSON is explicitly requested.
3. The console is a responsive workspace: conversation first, bounded activity
   drawer, status strip, and an inspector that docks on wide terminals and takes
   over the workspace on narrow terminals.
4. Slash commands have one metadata registry and shell-style parsing. Help,
   suggestions, validation, and execution consume the same definitions.
5. Engine observers receive an additive `run-finished` event. A cooperative
   cancellation callback may stop a run between states without interrupting a
   provider request in flight.

## Consequences

- Human terminal output improves without corrupting stdout contracts used by
  scripts and MCP remains unchanged.
- Unknown config/session/plugin failures become concise diagnostics; set
  `MKLANG_DEBUG=1` to expose a traceback.
- External event consumers must tolerate the new additive terminal event, as
  event streams are extensible by contract.
