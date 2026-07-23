# Distribution experiment: five-reader comprehension (D1 / issue #61)

**Status:** protocol frozen; **execution pending** (external readers — cannot
be run from inside the repository).

## Why this exists

Engineering maturity (27 ADRs, ~92% coverage, multi-platform CI, package 1.0.0)
has outrun distribution. This test is the one finding the 2026-07-23 validation
could not settle in-repo, and the one most likely to be rationalised away.

## Protocol (fixed in advance)

1. Pick **five** people or venues where a declarative LLM-state-machine DSL
   with a self-authoring console would plausibly land (e.g. agent-tooling
   Discord, local LLM meetup, a colleague who ships agent products, HN "Show
   HN" draft reviewer, a friend who uses Claude/Cursor daily).
2. Show them **only**:
   - the repository README
   - the two demo recordings (`agent`, `language` — see `docs/demos.md`)
3. **Do not explain.** Record, **verbatim**, the first question each person asks.
4. Optionally note whether they install / try anything within 24h.

## Metric & branches

| Outcome | Interpretation |
| --- | --- |
| ≥3 of 5 **do not** understand what mklang is *for* after README + demos | Positioning problem; no coverage ratcheting touches it. |
| ≥3 understand, but **nobody** tries it | The thing it does best (agents authoring verified deterministic workflows, ADR 0015) is buried in ADRs, absent from the pitch. |
| ≥3 understand **and** ≥1 installs | Distribution is working; the repo is simply young (falsifier of the "structural distribution failure" claim). |

## Results register

| # | Venue / person (role, not name) | First question (verbatim) | Understood "for"? | Tried install? |
| --- | --- | --- | --- | --- |
| 1 | _pending_ | | | |
| 2 | _pending_ | | | |
| 3 | _pending_ | | | |
| 4 | _pending_ | | | |
| 5 | _pending_ | | | |

**Headline (fill after run):** _n/5 understood · n/5 tried · branch: —_

## Related

- Validation report 2026-07-23 finding D1
- Issue #61
- ADR 0028 (1.0 provisional posture — depends on this + #59)
