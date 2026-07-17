# ADR 0019 — Live engine events on the MCP transport

Status: Accepted

## Context

The console (ADR 0015) consumes `engine.run(on_event=…)` in-process: state-by-
state progress renders while the run is in flight. Every other MCP client —
Claude Code, a future OpenTUI/Ink front-end, any agent host — still sees a
commissioned run as a black box until the result returns. The stack question
raised while planning the console UI ("more modern TUIs?") resolved to: keep
the bundled console on Textual, and buy the modern-client option at the layer
that lasts — the transport. Without events on the wire, an external client
would have to re-architect the engine; with them, it is just another renderer.

## Decision

`run` and `resume` forward the engine's `on_event` stream as **MCP logging
notifications**: logger `mklang.event`, message = the event dict as JSON
(`run-start` / `state-start` / `state-done` / `branch-done`, unchanged shape).
Purely additive — result shapes are untouched and clients that ignore logging
notifications see exactly the old behavior.

Scheduling detail that is easy to get wrong: FastMCP invokes sync tools on the
event loop itself, while fan-out branches emit from worker threads. The
forwarder therefore captures the running loop at tool-call time and schedules
`ctx.log(...)` with `asyncio.run_coroutine_threadsafe` — the one path safe
from any thread that never blocks the emitter. Like the engine's own observer
seam, forwarding is isolated: a transport hiccup can never affect the run.
Notifications emitted while a sync tool blocks the loop flush before the tool
result is sent, so clients still receive events → result in order.

A consequence for module hygiene: `mcp/server.py` drops
`from __future__ import annotations` so the `ctx: Context` parameter keeps a
real (non-string) annotation — FastMCP resolves injection by evaluating
annotations against module globals, and `Context` is imported lazily.

**[maybe] External console client** (OpenTUI/Ink class) is now a ROADMAP item
that needs no engine work: speak MCP, render `mklang.event` notifications.

## Consequences

- Any MCP client can render live run progress today; the bundled Textual
  console keeps its richer in-process seam.
- The event vocabulary is now a wire contract shared by two surfaces; changes
  to it must consider both (trace stays the canonical record).
- In-memory tests pin the stream (`logging_callback` on the client session):
  sequence starts with `run-start` and carries per-state completions.
