# ADR 0003 — Provider-agnostic: no provider/model pinning in a `.mk`

Status: Accepted

## Context

A `.mk` is meant to be a portable artifact — "the document is the program". Naming a
concrete provider or model id inside it (e.g. `model: claude-opus-4-8`) would bind
the machine to one vendor and break portability the moment someone runs it elsewhere.

## Decision

A `.mk` **never** names a provider or model. It references capability tiers only
(ADR 0001). Provider selection and the tier→model map live entirely in the host-side
runtime config; keys live in `.env`. Explicit pinning is a documented non-goal.

## Consequences

- Machines are portable across Anthropic, OpenAI, DeepSeek, OpenRouter, xAI, Mistral,
  and local models with zero edits.
- The runtime needs a config + adapter layer (delivered: native Anthropic + a generic
  OpenAI-compatible adapter covering the rest).
- If pinning is ever needed, it must arrive as an optional, clearly-marked escape
  hatch — the tier stays the portable default.
