# ADR 0016 — Host web-search tool: optional real binding, offline stub default

Status: Accepted (stub + fake/tavily + example; runtime.yaml tools block deferred)

## Context

`tool:` states and the host registry (`(dict) → str`, entry points `mklang.tools`)
are language-complete (SPEC §4.9). The reference builtin `search` must stay
honest offline while allowing production hosts to bind a real backend without
provider-native tool-calling or browser automation.

## Decision

1. **Protocol unchanged.** Web search is a host tool named `search`. Input:
   `{"query": "…", "max_results"?: N}`. Observation: a JSON string
   `{"query", "results":[{"title","url","snippet"}], "error": null|str}`.
2. **Default remains the offline stub** — no search API key on core install.
3. **Real binding is opt-in** via `mklang.search.configure_search` or env
   `MKLANG_SEARCH_BACKEND=fake|tavily` (+ `TAVILY_API_KEY` for Tavily).
   **Convenience:** if `TAVILY_API_KEY` is set and `MKLANG_SEARCH_BACKEND` is
   unset, Tavily is selected automatically (the key is the host opt-in).
   `MKLANG_SEARCH_BACKEND=stub` forces offline. Entry-point plugins may still
   override `search` entirely.
4. **No language change.** Example: `examples/research_web.mk` (+ scenario test).
5. **Threat model.** Search observations are **untrusted context** (SPEC §11).

## Checklist

| Item | Status |
|---|---|
| Structured stub default | **done** |
| Fake + Tavily backends | **done** |
| `research_web.mk` + scenario test | **done** |
| SPEC / patterns note | **done** |
| `runtime.yaml` tools.search block | deferred |
| Console-specific consent copy for search | deferred (generic tool consent covers it) |
| stdlib `std_research` | deferred |

## Consequences

- Authors write portable `tool: search` machines; demos work offline.
- Injection surface grows with web text — documented, not denied.
- Provider-native web tools stay out of core (ADR 0003).
