# ADR 0028 — Provisional posture of package 1.0.0

Status: Accepted

## Context

Package **1.0.0** shipped 2026-07-23 with a stated stability surface (ADR 0026)
and a hard `.mkl` rename (ADR 0027). The 2026-07-23 validation (finding **C1**)
measured that the entire example surface first appeared **2026-07-18** — about
five days of **author-only** exercise before the freeze, with **zero external
soak** on the spec-0.3 surface.

ADR 0026 already commits SemVer from 1.0.0 and freezes language 0.3. It does
**not** answer four judgement questions the validation left open:

1. What did 1.0.0 buy, concretely, at zero external users?
2. Under ADR 0026, what is the cost of a language change discovered to be needed?
3. Which of the spec-0.3 surface has been exercised by anyone other than the author?
4. Was an honest alternative `0.17.0` with 1.0.0 waiting for the first external issue?

Issue #62 sequences this decision **after** the authoring-loop magnitude (#59)
and the distribution test (#61). This ADR records the decision with the evidence
available: #59 measured in-repo; #61 remains an external protocol (cannot be
completed from inside the repository). Waiting forever for five external readers
before writing the posture would leave the freeze *defaulted into*, which is the
failure mode C1 exists to prevent.

## Decision

### 1. 1.0.0 stands — no retraction

Retracting 1.0.0 (re-tagging as 0.17.x) costs more than it recovers: PyPI
artifacts, the AUR pin, and the stability docs already point at 1.0.0. The
number is not a claim of market validation; it is a claim about **SemVer
discipline going forward** (ADR 0026).

### 2. What 1.0.0 bought (question 1)

At zero external users, 1.0.0 bought three concrete things:

- A **frozen language surface** (spec 0.3) with an explicit deprecation cycle
  for any future break.
- A **hard discovery cut** (`.mkl` only) taken at minimum rename cost.
- A **publish bar**: further churn is batchable behind tags; PyPI is for
  user-visible change (CONTRIBUTING publish cadence).

It did **not** buy external proof that the surface is the right one. That gap is
acknowledged, not papered over.

### 3. Cost of a needed language change (question 2)

Under ADR 0026:

| Change class | Cost |
| --- | --- |
| Additive, backward-compatible (new opt-in face, tooling) | MINOR |
| Breaking stable surface (language contract, host APIs in the stable list) | Deprecate in a MINOR → remove no sooner than the next MAJOR, after ≥1 full minor cycle |
| Spec bump (0.4+) | Its own release, gated by the conformance suite (ADR 0009) |

So a mistaken 1.0 freeze is **slow to reverse on the language face**, which is
exactly why this ADR names the conditions under which a 2.0 is acceptable
rather than pretending the freeze was fully soaked.

### 4. External exercise (question 3)

Measured at decision time: **none**. The example surface, demos, and live
gate-divergence suite are author-operated. Distribution experiment #61 is the
protocol that would change this number; until it runs, treat external exercise
as **unproven**, not as “fine because young.”

### 5. Honest alternative (question 4)

`0.17.0` then 1.0.0-on-first-external-issue was a coherent alternative **before**
the tag. After the tag, the honest posture is not time-travel: it is to keep
1.0.0 and mark the freeze **provisional on evidence**, not on marketing.

### 6. Conditions under which a 2.0 is acceptable

A MAJOR (2.0.0) that breaks the 1.0 stable surface is acceptable when **any** of:

1. **Authoring-loop magnitude** (issue #59 / B1): a **re-run** measures
   `blind_spot > 0.25` and forces a language/host change that cannot ship as
   opt-in (e.g. a required behavioural step between `save` and `run` that
   alters the 1.0 console/MCP contract in a breaking way). The 2026-07-23
   DeepSeek run recorded **blind_spot = 0.0167**
   (`docs/experiments/authoring-blind-spot.md`) — condition **not** met; do
   **not** build `test_machine` on that evidence.
2. **Distribution falsifier fails hard** (issue #61 / D1): ≥3 of 5 external
   readers cannot understand what mklang is *for* after README + demos **and**
   fixing the pitch requires a contract change (not only docs).
3. **Spec debt**: a conformance-gated 0.4+ language release that cannot remain
   a pure superset of 0.3 for the stable surface.

Absent those, prefer MINOR additive work and docs. Do not burn a MAJOR for
cosmetic refactors (`cmd_doctor`, presentation, host-only tooling).

### 7. Operational rule until #61 completes

- Treat the 1.0 surface as **stable for SemVer purposes** (ADR 0026 still binds).
- Treat **product confidence** as provisional: prioritise the five-reader test
  and any #59 follow-ups over further coverage ratcheting.
- Record new external soak (issues, installs, reader notes) in
  `docs/experiments/` so this ADR’s inputs can be revisited without archaeology.

## Consequences

- Positive: the freeze is a written decision, not a default; 2.0 criteria are
  falsifiable.
- Positive: no PyPI/AUR churn from a retraction.
- Negative: until #61 runs, distribution risk remains unmeasured; this ADR must
  not be cited as proof that distribution is fine.
- Follow-up: close #62 when this ADR lands; keep #61 open until the results
  register is filled; update §6 if #59’s verdict forces a product decision.
