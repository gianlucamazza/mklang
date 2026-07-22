# ADR 0016 — Host web-search tool: optional real binding, offline stub default

Status: Accepted (stub + fake/tavily + example; runtime.yaml tools block deferred).
Envelope generalized by [ADR 0020](./0020-host-tool-stub-architecture.md).

## Context

`tool:` states and the host registry (`(dict) → str`, entry points `mklang.tools`)
are language-complete (SPEC §4.9). The reference builtin `search` must stay
honest offline while allowing production hosts to bind a real backend without
provider-native tool-calling or browser automation.

## Decision

1. **Protocol unchanged.** Web search is a host tool named `search`. Input:
   `{"query": "…", "max_results"?: N, "days"?: N, "topic"?: "news"|"general"}`.
   Observation: a JSON string with ADR 0020 envelope fields
   `tool`, `stub`, `error` plus
   `query`, `results:[{title,url,snippet,published_date?}]` (and optional `message`).
   Recency fields are optional; backends that ignore them stay valid.
   Unbound / fake → `stub: true`; live Tavily → `stub: false`.
2. **Default remains the offline stub** — no search API key on core install.
3. **Real binding is opt-in** via `mklang.search.configure_search` or env
   `MKLANG_SEARCH_BACKEND=fake|tavily` (+ `TAVILY_API_KEY` for Tavily).
   **Convenience:** if `TAVILY_API_KEY` is set and `MKLANG_SEARCH_BACKEND` is
   unset, Tavily is selected automatically (the key is the host opt-in).
   `MKLANG_SEARCH_BACKEND=stub` forces offline. Entry-point plugins may still
   override `search` entirely.
4. **No language change.** Example: `examples/research_web.mk` (+ scenario test).
   Time-sensitive machines declare `context.today: ""`; hosts fill empty
   declared `today` with the ISO date (host convention, not a SPEC face).
   Wall-clock machines may also declare `context.now: ""` for a local ISO
   datetime fill (same inject path; not a search concern).
5. **Threat model.** Search observations are **untrusted context** (SPEC §11).

## Checklist

| Item                                                | Status                                           |
| --------------------------------------------------- | ------------------------------------------------ |
| Structured stub default                             | **done**                                         |
| Fake + Tavily backends                              | **done**                                         |
| `research_web.mk` + scenario test                   | **done**                                         |
| SPEC / patterns note                                | **done**                                         |
| Optional `days` / `topic` / `published_date`        | **done**                                         |
| Host `context.today` convention + research patterns | **done**                                         |
| Host `context.now` (wall-clock local ISO datetime)  | **done** (same inject path; not search-specific) |
| `runtime.yaml` tools.search block                   | **done** (generalized `tools:` block, see below) |
| Console-specific consent copy for search            | deferred (generic tool consent covers it)        |
| stdlib `std_research`                               | shipped (search → ground stdlib machine)         |

## The `tools:` block (shipped later, generalized)

`runtime.yaml` may declare backend bindings for every builtin host tool, not
just search:

```yaml
tools:
  search: { backend: stub | fake | tavily }
  kb: { backend: stub | fake }
  mail: { backend: stub | fake }
  fs: { backend: stub | local, workspace: <path>, write: true | false }
```

Precedence per knob, echoing ADR 0023's per-key layering:
`configure_*()` programmatic binding > explicit `MKLANG_*` env var >
`tools:` config > built-in default. The env var is the operator's
per-invocation override; the config is the persistent host/project
declaration. The `TAVILY_API_KEY` auto-select is part of the _default_ tier,
so `tools.search.backend: stub` is a persistent off-switch. There is no
`api_key` knob by design — secrets stay in the layered `.env` (ADR 0023).
A project-layer `tools.fs.write: true` is a standing write grant checked in
from a repo; equivalent exposure already existed via a project `.env`
`MKLANG_FS_WRITE=1`, and `mklang doctor` prints every binding **with its
deciding source** (`env` / `config` / `default`) so the grant is visible.
`mklang test`/scripttest never loads a runtime config; scripted tools stay
env-driven.

## Consequences

- Authors write portable `tool: search` machines; demos work offline.
- Injection surface grows with web text — documented, not denied.
- Provider-native web tools stay out of core (ADR 0003).
