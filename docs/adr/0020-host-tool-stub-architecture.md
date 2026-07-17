# ADR 0020 — Host tool stub architecture

Status: Accepted

## Context

Host tools are language-complete as opaque `(dict) → str` callables (SPEC §4.9).
ADR 0016 gave `search` an honest offline default (structured JSON, opt-in live
backend). Showcase tools `search_kb` and `send_reply` remained free-text stubs
and, for `send_reply`, *looked* like a successful real send (`[sent] …`).

Authors, console agents, and gates need a uniform way to tell **stub / fake /
live** without language changes.

## Decision

1. **Envelope for I/O tools.** Reference tools that touch external systems or
   side effects return a JSON string with stable fields:
   - `tool` — name
   - `stub` — `true` if no real external system was used
   - `error` — string or `null`
   - tool-specific payload (`results`, `facts`, `sent`, …)

   Helper: `mklang.tool_obs.tool_obs`.

2. **Binding tiers** (per I/O tool):

   | Tier | Meaning | Opt-in |
   | --- | --- | --- |
   | stub | Default; honest no-op / demo payload | always |
   | fake | Deterministic in-process demo | env / `configure_*` |
   | live | Real network / delivery | key / env / entry-point override |

3. **Tool mapping**

   | Tool | Default | Fake | Live (reference) |
   | --- | --- | --- | --- |
   | `search` | unbound JSON + enablement message | `FakeSearchBackend` | Tavily |
   | `search_kb` | demo policy facts, `stub: true` | `FakeKBBackend` | none (entry point) |
   | `send_reply` | `sent: false`, `delivery: "stub"` | in-memory, `delivery: "fake"` | none (entry point) |
   | `calc` | pure offline arithmetic — **not** this envelope | n/a | n/a |

4. **No language change.** Machines keep `tool: <name>`; hosts bind backends.

5. **Env**

   - `MKLANG_SEARCH_BACKEND=stub|fake|tavily` (existing)
   - `MKLANG_KB_BACKEND=stub|fake`
   - `MKLANG_MAIL_BACKEND=stub|fake`

## Consequences

- Offline demos never imply live web/mail.
- Gates and console agents can read `stub` / `error` / `sent` in observations.
- Scenario tests that script tool outputs are unchanged.
- Breaking change only for hosts that parsed free-text `[kb stub]` / `[sent]`
  formats (documented in CHANGELOG).
