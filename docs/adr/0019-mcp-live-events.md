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

Scheduling detail that is easy to get wrong under MCP SDK v2: plain `def`
tools run on a **worker thread** (no running event loop), while fan-out
branches also emit from workers. `run` / `resume` are therefore `async def`
so the forwarder can capture the server loop on the tool body, and the
blocking `engine.run` is offloaded with `asyncio.to_thread`. Events still
schedule `ctx.log(...)` via `asyncio.run_coroutine_threadsafe` — the one path
safe from any thread that never blocks the emitter. Like the engine's own
observer seam, forwarding is isolated: a transport hiccup can never affect
the run.

Context injection still needs a real (non-string) `Context` annotation in
module globals; `from __future__ import annotations` stringifies it, so the
type is imported at module load (with a no-extra placeholder).

Protocol note (SEP-2577, 2026-07-28): MCP-level logging is **deprecated but
still delivered**. Clients on modern links must opt in (`log_level=…` on the
SDK `Client`). Replacing this channel (e.g. subscriptions) is a follow-up
when hosts reliably consume an alternative; the wire logger name and JSON
payload stay the contract until then.

**[maybe] External console client** (OpenTUI/Ink class) is now a ROADMAP item
that needs no engine work: speak MCP, render `mklang.event` notifications.

## Consequences

- Any MCP client can render live run progress today; the bundled Textual
  console keeps its richer in-process seam.
- The event vocabulary is now a wire contract shared by two surfaces; changes
  to it must consider both (trace stays the canonical record).
- In-memory tests pin the stream (`logging_callback` on the client session):
  sequence starts with `run-start` and carries per-state completions.
