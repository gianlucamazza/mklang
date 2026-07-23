# Validation Report — 2026-07-23 audit findings

**Subject:** `gianlucamazza/mklang` @ `e525a1b` (v1.0.0)
**Executed:** 2026-07-23, on a clean clone in an offline-capable environment.
**Plan:** the twelve-finding *Problem Validation Plan* (Method §0). This report fills the
plan's §4 Results register and derives a fix backlog from the verdicts. It prescribes no
fixes beyond that backlog, per the plan's method.

## Environment constraint (read first)

The **original audit run** had **no provider API keys** (`DEEPSEEK_API_KEY` /
`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` all unset). That bounded three items to
*code-and-record* evidence rather than fresh live execution at first write.

**Same-day / next-session follow-ups** (keys present for DeepSeek + OpenAI):

- **B1 / B2** — measured; see `authoring-blind-spot.md` and the register below.
- **C3** — still not re-run with Anthropic (`ANTHROPIC_API_KEY` unset / billing);
  the recorded DeepSeek+OpenAI 2026-07-23 suite remains the baseline.
- **D1** — still external; protocol frozen in `distribution-five-reader.md`.

Nothing below reports a magnitude that was not actually measured.

---

## 4. Results register

| ID | Verdict | Evidence | Falsifier triggered? | Follow-up |
|---|---|---|---|---|
| A1 | **CONFIRMED; CI fixed** | At audit: `quality.yml` ran `ruff check` only; one file drifted. Follow-up: `Format check` step + reformatted file (#58). | No | **DONE** — `ruff format --check` in `quality.yml`. |
| A2 | **CONFIRMED; docs fixed** | `--extra dev`: **87.58% FAIL** vs `--extra dev --extra mcp`: **91.81% PASS**. Follow-up: CONTRIBUTING documents gate 90 + `--extra mcp`. | No | **DONE** — canonical invocation documented. |
| A3 | **CONFIRMED; invariant enforced** | Three-way divergence at audit (23 tags / 28 CHANGELOG / 16 PyPI). Follow-up: tag↔CHANGELOG ≥0.5.3 test + `fetch-depth: 0` (#58). | No | **DONE** — `tests/test_release.py` + CI tags. |
| A4 | **DOWNGRADE (mostly cosmetic); hotspot fixed** | At audit: 1026 lines / mean CC 8.05 (B); hotspot **`cmd_doctor` CC 41 (F)**. Follow-up: helpers extracted — `cmd_doctor` CC **8 (B)** (#63). | **Partial** at audit; hotspot closed. | Do not split `cli.py` wholesale. |
| B1 | **CONFIRMED (structural); magnitude MEASURED** | Structural premise unchanged. Live run 2026-07-23: DeepSeek `deepseek-reasoner`, 20 corpus items × 3, `blind_spot = 0.0167` (check 0.7167 − behaviour 0.7000). Verdict: **do not build `test_machine`**. See `authoring-blind-spot.md`. | Falsifier for “must build test_machine” **triggered** (spot < 0.10). | Close #59 on measurement; keep authoring-reliability work separate. |
| B2 | **CONFIRMED (structural); magnitude MEASURED** | Same harness: 41.7% of trials needed ≥1 static repair; 28.3% still failed check after one repair. Shared `budget: 16` remains optimistic for multi-gate authoring — orthogonal to `test_machine`. | n/a | Optional: dedicated authoring-repair budget (product), not a language break. |
| B3 | **CONFIRMED asymmetry — but DELIBERATE & documented → close by-design** | MCP tools: `run, resume, list_machines, describe_machine, check` — no write. Author-and-run works (`run(source=…)` + `check`). ADR 0011: "a remote MCP host should not touch the server's filesystem… introduces no new authority." ADR 0013:53: "ADR 0011's 'never write to disk' default is preserved." | **Yes** — "deliberate" branch: it *was* withheld, on purpose. "undocumented" sub-claim refuted. | One-line surfacing in SECURITY.md / SPEC §11 (ADR trail is the current home). |
| C1 | **Judgement — decided (ADR 0028)** | Whole example surface first appeared **2026-07-18** (`git log --follow`), 5 days before the 1.0.0 freeze (2026-07-23). Author-only soak; zero external. (Naïve `--diff-filter=A` showed 2026-07-23 — a `.mk→.mkl` rename artifact; corrected.) | n/a (J) | ADR 0028: freeze provisional on evidence; 2.0 conditions named; no retraction. |
| C2 | **CONFIRMED (observation); policy set** | `v0.16.0` 14:48 and `v1.0.0` 17:34 **same day** (+0200 ≈ plan's UTC 12:51/15:40). 16 PyPI releases across 2026-07-16…23. | No | Publish-cadence policy in CONTRIBUTING (done on the validation PR). |
| C3 | **CONFIRMED via recorded run; BLOCKED (live re-run)** | `gate-divergence.md` records 2026-07-23 four-machine suite: **1.0 agreement per machine** (15/15 pairs each), 24/24 runs done, zero gate errors, deepseek+openai ×3. Per-machine breakdown present. | **Coarse-routing critique pre-addressed** — `sentiment_borderline` (deliberately contestable) is already in the suite; routing stayed 1.0 while free-text diverged. | Price Anthropic gap: one 4-machine×3 pass ≈ **~30k tokens / < $1**; blocker is account credit, not cost-at-scale. |
| C4 | **CONFIRMED bus factor 1** | `git shortlog`: 124 + 54 commits one human (two spellings), 8 Claude, 2+2 bots. | n/a (J) | No action now; confirm CONTRIBUTING answers "how does a 2nd person get productive." |
| D1 | **BLOCKED (external)** | Cannot be validated from inside the repo — needs 5 external readers. Internal facts consistent with the claim: 11 examples, 28 ADRs, ~92% cov, 5-platform matrix; protocol frozen in `distribution-five-reader.md`. | Not evaluable in-repo | Run the 5-reader test (record verbatim first questions). |

---

## Per-item detail

### A1 — Format gate absent — CONFIRMED
- `uv run --extra dev ruff format --check src tests scripts` → *"1 file would be reformatted"*
  (`tests/test_truncation.py`), 92 already formatted.
- **Falsifier checked and refuted:** the reformat reproduces under the version the repo
  resolves for CI — `uv run ... ruff --version` → **0.15.22** (same as the original local
  observation). Not a local-version artifact.
- **Second question:** `git log --all --grep=format -i` surfaces only unrelated commits (docs
  alignment, taint fences, logging). **No recorded rationale** for omitting the format check.
- At audit, `quality.yml` was `ruff check` only (no format gate).
- **Follow-up:** `Format check` step added (`ruff format --check src tests scripts`);
  drifted `tests/test_truncation.py` reformatted (#58).

### A2 — Coverage gate is environment-dependent — CONFIRMED; docs fixed
- Leg 1 (`--extra dev`): TOTAL **87.58%**, *"Required test coverage of 90.0% not reached"* → FAIL.
- Leg 2 (`--extra dev --extra mcp`): TOTAL **91.81%** → PASS. `mcp/server.py` goes 0% → 87%.
- **Follow-up:** CONTRIBUTING documents the canonical
  `uv run --extra dev --extra mcp pytest …` invocation and `fail_under = 90`.

### A3 — Tag / CHANGELOG / PyPI divergence — CONFIRMED; invariant enforced
- Counts at audit: **23 tags, 28 CHANGELOG entries, 16 PyPI releases** (three-way).
- CHANGELOG-only (never tagged): `0.1, 0.2.0, 0.2.1, 0.5.1, 0.5.2` — pre-distribution history.
- **Follow-up:** invariant cut at **0.5.3** in `tests/test_release.py`; CI
  `fetch-depth: 0` so the test runs (does not skip) on the matrix (#58).

### A4 — `cli.py` monolith — DOWNGRADE to cosmetic; hotspot fixed
- At audit: Radon mean CC **8.05 (B)**; outlier **`cmd_doctor` CC 41 (F)**; three C-grade
  handlers (`cmd_resume` 20, `cmd_lint` 16, `cmd_test` 12). Dispatch-table shape confirmed.
- **Follow-up:** `cmd_doctor` extracted into helpers — CC **8 (B)** (#63). Rest of `cli.py`
  left alone.

### B1 — Structural ≠ behavioural validation — CONFIRMED (structural); magnitude MEASURED
- **Mechanism proven from source, provider-free:**
  - `host.check_machine` (host.py:140) docstring: *"Validate without running — schema +
    semantics + lint, no provider needed."* Body = `_parse_source` + `semantic_check` +
    `lint_machine`. Purely static.
  - `console/tools.py:140 write_machine` writes the file, then returns
    `host.check_machine(source=…)` as its verdict.
  - `agent.mkl` loop: `decide → author → save → decide`. `save` observation carries the
    static check; control returns to `decide`. **No state executes the authored machine
    against a scenario before `reply`.**
  - **No `test_machine` exists** anywhere in `src/`. The `mklang test` / `scripttest` runner
    is a separate CLI path, not wired into the authoring loop.
- So the plan's core assertion — the loop "cannot distinguish valid from correct" — is
  **true by construction.**
- **Follow-up (same day, keys available):** corpus + harness + live DeepSeek
  `deepseek-reasoner` run (20×3) → **`blind_spot = 0.0167`**. Verdict under the fixed
  thresholds: **do not build `test_machine`.** Recorded in
  `docs/experiments/authoring-blind-spot.md`; issue #59 closed.

### B2 — Repair-pass sufficiency — CONFIRMED (structural); magnitude MEASURED
- `agent.mkl:19 budget: 16 # decide/action cycles incl. an authoring repair + the reply`.
- **Structural observation supporting the concern:** there is no *dedicated* repair budget.
  A turn that discovers + runs a machine or two, then authors and needs a *second* repair,
  draws every step from the same pool of 16. The comment implies headroom for *one* repair;
  the code does not reserve it.
- **Follow-up:** same harness measured 41.7% of trials needing ≥1 static re-author and
  28.3% still failing check after one repair — authoring reliability, orthogonal to
  `test_machine`.

### B3 — MCP persistence asymmetry — CONFIRMED asymmetry, DELIBERATE → close by-design
- Surface: `run, resume, list_machines, describe_machine, check`. `run(source=…)` +
  `check(source=…)` give author-validate-run; **no persist**.
- **Was it withheld?** Yes, deliberately, and it is recorded:
  - ADR 0011: *"A remote MCP host should not touch the server's filesystem… never written to
    disk unless explicitly requested"*; *"introduces no new authority."*
  - ADR 0013:53: *"ADR 0011's 'never write to disk' default is preserved; persistence is an
    explicit per-call opt-in."*
  - ADR 0013:45: an MCP host may *"discover… validate a machine it authored, run it"* — the
    surface is scoped to exactly that, minus workspace persistence.
- The plan's "undocumented asymmetry" framing is the part that fails: it **is** documented in
  the ADR trail. The console's guard model (workspace confinement, human `confirm` on
  overwrite) indeed does not transfer to a headless host — and the ADRs already chose *not* to
  pretend it does. **Close as by-design;** optional one-liner in SECURITY.md / SPEC §11 for
  discoverability outside the ADR trail.

### C1 — Premature 1.0.0 — decision recorded (ADR 0028)
- **Q3 (soak time), measured:** every example first appeared **2026-07-18** (via
  `git log --follow`, correcting a `.mk→.mkl` rename that made naïve dating read 2026-07-23).
  Five days of **author-only** exercise; no external soak on any part of the spec-0.3 surface.
- **Follow-up:** ADR 0028 records the posture — 1.0.0 stands (no retraction), freeze is
  SemVer-stable under ADR 0026 and provisional on evidence for product confidence, with
  falsifiable 2.0 conditions. Issue #62 closed. Distribution evidence (#61) still open.

### C2 — Release cadence — CONFIRMED observation; policy set
- `git for-each-ref` timeline: `v0.16.0` 2026-07-23 14:48, `v1.0.0` 2026-07-23 17:34 — under
  three hours apart, same day. 16 PyPI publishes in the repo's ~7-day tag history.
- **Follow-up:** CONTRIBUTING Releases now states publish cadence (PyPI on user-visible
  change or a fixed interval, whichever is slower; a tag alone is enough for a checkpoint).

### C3 — Provider coverage — CONFIRMED via recorded run; live re-run BLOCKED
- `docs/experiments/gate-divergence.md` Results table records the post-freeze **2026-07-23**
  four-machine suite: **1.0 agreement per machine** (15/15 within-machine pairs each), 24/24
  runs `done`, zero gate errors, deepseek + openai ×3. Per-machine signatures recorded.
- **Coarse-routing critique is pre-addressed:** the suite already carries a deliberately
  contestable machine (`sentiment_borderline`, "genuinely contestable" gates) plus a
  control-flow-critical `severity_escalate` and a `grounding_repair` loop. The recorded note —
  *"free-text outputs diverge on the contestable machines while routing stays identical"* — is
  precisely the reassurance the plan asked for: agreement is not measured only on easy cases.
- **Anthropic priced:** billing-blocked, not key-blocked (SPEC §9, README, experiment doc all
  say so). One four-machine × 3-repeat Anthropic pass is ~12 small synthetic runs ≈ **~30k
  tokens, well under \$1**. The decision to leave it blocked is therefore a credit-purchase
  choice, not a cost-at-scale one.

### C4 — Bus factor 1 — CONFIRMED, no action now
- `git shortlog -sne`: 124 + 54 (one human), 8 Claude, 2 dependabot, 2 github-actions.
- Not a defect pre-adoption. The ADR trail (27) + conformance suite already do most of the
  onboarding work; confirm CONTRIBUTING closes the loop.

### D1 — Distribution is the binding constraint — BLOCKED (external)
- Un-testable from inside the repository by design. Internal facts are consistent with the
  claim (mature engineering: 28 ADRs, ~92% cov, 5-platform matrix; zero external signal),
  but the claim's *own* falsifier is external: show two demos to five people, record their
  first verbatim question, count how many understand it unaided, and whether ≥1 installs.
  Protocol: `distribution-five-reader.md`. That test is cheap and owed; it cannot be run here.

---

## Decisions still owed (J-class — must be recorded as ADRs, not defaulted)

Per the plan's Method rule, no J-item enters a fix backlog until its decision is recorded.

1. **C1** — provisional-freeze ADR. **Done (ADR 0028)** after B1 measurement; D1 still
   external. 1.0.0 stands; 2.0 conditions named; no retraction.
2. **C2** — cadence policy in CONTRIBUTING. **Done** — "Publish cadence" added to the Releases
   section (the plan's candidate wording; maintainer may tune the interval).
3. **C4** — acknowledge in CONTRIBUTING; no code. The change checklist + ADR trail already
   answer "how a second person gets productive"; no further action taken.

### Best-practices documentation completed (this branch)

The findings surfaced three gaps in `docs/guides/best-practices.md`, now filled:

- **B1** — §10 gains "Static checks are not behavioural correctness" (and §15 anti-pattern
  #16): `check`/`lint` prove well-formedness, not behaviour; run a scenario, especially for
  agent-authored machines.
- **B3** — §11 + §14 now state the MCP **read-only-to-disk** posture (ADR 0011/0013).
- **A1** — CONTRIBUTING dev loop + change checklist now include the CI-gated `ruff format`.
- **A3** — CONTRIBUTING Releases now documents the tag↔CHANGELOG invariant enforced by the test.

## Derived fix backlog (T/M-class — verdict-driven)

Items marked **DONE** were fixed on this branch alongside the report.

| From | Action | Size | Status |
|---|---|---|---|
| A1 | Reformat `tests/test_truncation.py` (**DONE**); add `ruff format --check` to `quality.yml` lint step (**DONE** — #58). | XS | **DONE** |
| A2 | Fix stale `fail_under = 88` → `90` in CONTRIBUTING (2×); note the `--extra mcp` requirement. (Canonical command already documented; that was the real residual.) | S | **DONE** |
| A3 | Enforce the tag↔CHANGELOG invariant (cut at 0.5.3) in `tests/test_release.py` (**DONE**); `fetch-depth: 0` on the test-job checkout so CI sees tags (**DONE** — #58). The test skips (not fails) without tags, so it is safe for sdist installs. | S | **DONE** |
| B3 | One-line MCP no-persist note in SECURITY.md (ADR-decided). | XS | **DONE** |
| A4 | (Optional) refactor only `cmd_doctor` (CC 41). Do **not** split `cli.py` wholesale. | S | **DONE** — CC 41→8 (B); helpers in `cli.py` |
| B1 | Freeze the authoring corpus + hand-written acceptance scenarios; run the blind_spot experiment. | L | **DONE** — `blind_spot=0.0167`; no `test_machine` |
| C3 | (When credited) run one Anthropic four-machine pass (~30k tok) to close the three-provider gap. | XS | Blocked (`ANTHROPIC_API_KEY` unset / billing) |
| D1 | Run the five-reader comprehension test; record verbatim first questions. | M | Protocol frozen (`distribution-five-reader.md`); execution external |

### CI enforcements (applied — closes #58)

Both workflow edits land with this branch (maintainer push; the automation
account that wrote the report lacked `workflows` permission):

- **A1** — `Format check` step after `Lint` in the `checks` job
  (`ruff format --check src tests scripts`).
- **A3** — `fetch-depth: 0` on the `test` job checkout so
  `test_changelog_entries_from_distribution_cutoff_are_tagged` runs (does not
  skip) in CI.

---

## 5. Assumptions revisited (plan §5)

- **"The weakness is in distribution and the authoring loop, not code quality."** Partly
  revised by follow-up measurement: code quality remains *good*; B1's **blind_spot is
  tiny (0.0167)** so the structural authoring-loop gap does **not** dominate product risk
  the way the audit hypothesized. Residual authoring pain is **static-check failure /
  repair rate**, not silent behavioural wrongness. Distribution (D1) is still unmeasured
  and remains the open external risk.
- **"`blind_spot` is measurable with hand-written acceptance criteria."** **Confirmed** —
  the corpus + harness ran; writing criteria first was feasible. One true blind-spot trial
  out of 60.
- **Severity ordering (B1, D1 above all).** After measurement, **D1 outranks B1**. Next
  human priority: five external readers (#61). Optional: authoring-repair budget product
  work. Not more in-repo coverage ratcheting.
