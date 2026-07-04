# ADR 0005 — Reasoning is first-class and traced

Status: Accepted

## Context

Chain-of-Thought could be left implicit ("reason step by step" inside a prompt). But
then the reasoning is invisible (not in the trace) and its handling varies per author.
Modern models also expose native "thinking" we'd want to use uniformly.

## Decision

`reason: true` is an optional state face. When set, the runtime elicits a private
chain-of-thought that is (a) recorded in the trace step as `reasoning`, (b) visible to
that state's gates, and (c) **not** deposited into the context — only the `output` is.
On providers with native thinking (Anthropic adaptive, DeepSeek reasoner, o-series)
it maps to that capability; otherwise it prompts a scratchpad.

## Consequences

- CoT and ReAct become observable primitives, not prompt conventions.
- Reasoning doesn't leak into downstream prompts (keeps context clean); to pass it
  on, a dedicated state can make the reasoning its `output`.
- On plain models the scratchpad may be empty in the trace (the model still reasons
  internally) — an acceptable, provider-dependent limitation.
