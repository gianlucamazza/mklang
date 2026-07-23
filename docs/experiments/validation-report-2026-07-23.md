# Validation Report — 2026-07-23 audit findings

**Subject:** `gianlucamazza/mklang` @ `e525a1b` (v1.0.0)
**Executed:** 2026-07-23, on a clean clone in an offline-capable environment.
**Plan:** the twelve-finding *Problem Validation Plan* (Method §0). This report fills the
plan's §4 Results register and derives a fix backlog from the verdicts. It prescribes no
fixes beyond that backlog, per the plan's method.

## Environment constraint (read first)

This run had **no provider API keys** (`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY` all unset). That bounds three items to *code-and-record* evidence rather
than fresh live execution:

- **B1 / B2** — the `blind_spot` and repair-frequency *magnitudes* need ~60 reasoning-tier
  calls. Their **structural premises are settled from source**; their numbers are not.
- **C3** — cannot be *re-reproduced* live; settled instead from the **recorded** post-freeze
  run in `docs/experiments/gate-divergence.md` (dated the same day as this audit).

Every such item is marked **BLOCKED (live)** with the exact resource needed. Nothing below is
inferred where a command could have decided it, and no magnitude is reported that was not
actually measured.

---

## 4. Results register

| ID | Verdict | Evidence | Falsifier triggered? | Follow-up |
|---|---|---|---|---|
| A1 | **CONFIRMED** | `ruff format --check` reformats `tests/test_truncation.py`; reproduced on the CI-resolved ruff **0.15.22**; `quality.yml:24` runs `ruff check` only (no `format --check`); no rationale in `git log --grep=format`. | No | Add `ruff format --check` to the lint step. |
| A2 | **CONFIRMED** | `--extra dev`: **87.58% → FAIL** (fail_under=90). `--extra dev --extra mcp`: **91.81% → PASS**. Mechanism: `mcp/server.py` (184 stmts) is 0% without the extra. | No | Document the canonical invocation, or gate conditionally, or promote `mcp` to core. Decide one. |
| A3 | **CONFIRMED** | Three-way divergence: **23 tags / 28 CHANGELOG entries / 16 PyPI releases**. CHANGELOG-only (untagged): `0.1, 0.2.0, 0.2.1, 0.5.1, 0.5.2`. Tagged-but-unpublished: 7 (incl. `v0.8.1`, `v0.9.0`). | No | Pick an invariant, enforce in `tests/test_release.py` (has version-sync tests, no tag/changelog invariant yet). |
| A4 | **DOWNGRADE (mostly cosmetic)** | 1026 lines / 507 stmts / 87% cov. Mean CC **8.05 (B)**, but median low: most `cmd_*` handlers grade A/B. One real hotspot: **`cmd_doctor` CC 41 (F)**; `cmd_resume` (20), `cmd_lint` (16), `cmd_test` (12) grade C. | **Partial** — dispatch-table shape confirmed; falsifier not *fully* met (cmd_doctor). | Close the "monolith" framing; narrow refactor ticket for `cmd_doctor` only. |
| B1 | **CONFIRMED (structural); BLOCKED (magnitude)** | `host.check_machine` is "schema + semantics + lint, no provider needed" (host.py:140). `save` → `write_machine` returns that static verdict; the loop returns to `decide`. **No state runs the authored machine before `reply`.** No `test_machine` exists. So the loop cannot distinguish *valid* from *correct*. `blind_spot` not measured — no keys. | Not evaluable (magnitude un-run) | Run the frozen-corpus experiment when a provider key exists (~60 reasoning calls, DeepSeek). |
| B2 | **CONFIRMED (structural); BLOCKED (magnitude)** | `agent.mkl:19 budget: 16 # …incl. an authoring repair`. One shared budget covers *all* turn cycles (discover/run/clarify/author/save/reply) **plus** repairs — no dedicated repair budget. Repair frequency not measured — rides on B1. | Not evaluable (magnitude un-run) | Instrument passes-to-valid in the B1 harness. |
| B3 | **CONFIRMED asymmetry — but DELIBERATE & documented → close by-design** | MCP tools: `run, resume, list_machines, describe_machine, check` — no write. Author-and-run works (`run(source=…)` + `check`). ADR 0011: "a remote MCP host should not touch the server's filesystem… introduces no new authority." ADR 0013:53: "ADR 0011's 'never write to disk' default is preserved." | **Yes** — "deliberate" branch: it *was* withheld, on purpose. "undocumented" sub-claim refuted. | One-line surfacing in SECURITY.md / SPEC §11 (ADR trail is the current home). |
| C1 | **Judgement — decision owed** | Whole example surface first appeared **2026-07-18** (`git log --follow`), 5 days before the 1.0.0 freeze (2026-07-23). Author-only soak; zero external. (Naïve `--diff-filter=A` showed 2026-07-23 — a `.mk→.mkl` rename artifact; corrected.) | n/a (J) | ADR stating the freeze is *provisional*, naming conditions for 2.0 (see §Decisions). |
| C2 | **CONFIRMED (observation); decision owed** | `v0.16.0` 14:48 and `v1.0.0` 17:34 **same day** (+0200 ≈ plan's UTC 12:51/15:40). 16 PyPI releases across 2026-07-16…23. | No | Set an explicit PyPI cadence policy in CONTRIBUTING. |
| C3 | **CONFIRMED via recorded run; BLOCKED (live re-run)** | `gate-divergence.md` records 2026-07-23 four-machine suite: **1.0 agreement per machine** (15/15 pairs each), 24/24 runs done, zero gate errors, deepseek+openai ×3. Per-machine breakdown present. | **Coarse-routing critique pre-addressed** — `sentiment_borderline` (deliberately contestable) is already in the suite; routing stayed 1.0 while free-text diverged. | Price Anthropic gap: one 4-machine×3 pass ≈ **~30k tokens / < $1**; blocker is account credit, not cost-at-scale. |
| C4 | **CONFIRMED bus factor 1** | `git shortlog`: 124 + 54 commits one human (two spellings), 8 Claude, 2+2 bots. | n/a (J) | No action now; confirm CONTRIBUTING answers "how does a 2nd person get productive." |
| D1 | **BLOCKED (external)** | Cannot be validated from inside the repo — needs 5 external readers. Internal facts consistent with the claim: 11 examples, 27 ADRs, 91.81% cov, 5-platform matrix, repo age 5–7 days. | Not evaluable in-repo | Run the 5-reader test (record verbatim first questions). |

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
- `quality.yml:24` is `ruff check src tests scripts` — lint only.
- **Decision gate → add the check.** Drift confirmed + no rationale ⇒ add `ruff format --check`
  to the Lint step.

### A2 — Coverage gate is environment-dependent — CONFIRMED
- Leg 1 (`--extra dev`): TOTAL **87.58%**, *"Required test coverage of 90.0% not reached"* → FAIL.
- Leg 2 (`--extra dev --extra mcp`): TOTAL **91.81%** → PASS. `mcp/server.py` goes 0% → 87%.
- A first-time contributor running the *documented* dev command hits a red gate through no
  fault of their own. **Open question is real; pick one option** (document canonical
  invocation / conditional `fail_under` / promote `mcp` to core — as `textual` was in 0.15.0).

### A3 — Tag / CHANGELOG / PyPI divergence — CONFIRMED
- Counts: **23 tags, 28 CHANGELOG entries, 16 PyPI releases** (three-way).
- CHANGELOG-only (never tagged): `0.1, 0.2.0, 0.2.1, 0.5.1, 0.5.2` — the plan's specific
  A3 claim (0.5.1 / 0.5.2 untagged) is exactly reproduced.
- Note the candidate invariant *"every CHANGELOG entry above 0.5.0 has a tag"* is itself
  **violated** by 0.5.1/0.5.2 — so the invariant must be phrased ≥0.5.3 (pre-distribution
  cut at 0.5.2), or those two must be retro-tagged. Decide, then enforce in
  `tests/test_release.py`.

### A4 — `cli.py` monolith — DOWNGRADE to cosmetic (one hotspot)
- Radon: 20 blocks, **mean CC 8.05 (B)**. Distribution is bimodal: a long tail of A/B
  subcommand handlers (dispatch-table shape) **plus** one outlier — `cmd_doctor` **CC 41 (F)**
  — and three C-grade handlers (`cmd_resume` 20, `cmd_lint` 16, `cmd_test` 12).
- Raw: 917 SLOC, comments 2%.
- **Verdict:** the "largest module / weakest-covered" alarm is *mostly* a line-count optical
  illusion — the file is a dispatch table. The falsifier ("low complexity everywhere") is
  **partially** met: it holds for every handler except `cmd_doctor`. Close the monolith
  framing; open a narrow ticket for `cmd_doctor` if its 41 warrants it.

### B1 — Structural ≠ behavioural validation — CONFIRMED (structural); magnitude BLOCKED
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
  **true by construction.** What remains unmeasured is *how often* that gap bites
  (`blind_spot`), which is the entire quantitative decision (build `test_machine`? mandatory
  vs opt-in?). That needs live reasoning-tier runs.
- **To run when unblocked:** freeze `docs/experiments/authoring-corpus.yaml` (20 requests
  across the language's shapes), hand-write acceptance `.test.yaml` scenarios *first*, drive
  `ConsoleTools` with a fake `Bridge` (per `tests/test_console_tools.py`), run each authored
  machine through `scripttest.py`. Report `blind_spot = check_pass − behaviour_pass` against
  the plan's thresholds (<0.10 close / 0.10–0.25 opt-in tool / >0.25 required step + 1.1.0
  headline). Budget ~60 DeepSeek reasoning calls.

### B2 — Repair-pass sufficiency — CONFIRMED (structural); magnitude BLOCKED
- `agent.mkl:19 budget: 16 # decide/action cycles incl. an authoring repair + the reply`.
- **Structural observation supporting the concern:** there is no *dedicated* repair budget.
  A turn that discovers + runs a machine or two, then authors and needs a *second* repair,
  draws every step from the same pool of 16. The comment implies headroom for *one* repair;
  the code does not reserve it.
- Frequency (fraction needing a 2nd repair; fraction exhausting budget) rides on the B1
  harness and is unmeasured here.

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

### C1 — Premature 1.0.0 — decision owed
- **Q3 (soak time), measured:** every example first appeared **2026-07-18** (via
  `git log --follow`, correcting a `.mk→.mkl` rename that made naïve dating read 2026-07-23).
  Five days of **author-only** exercise; no external soak on any part of the spec-0.3 surface.
- Q1/Q2/Q4 are unpriced strategy questions (see §Decisions). The measured Q3 result supports
  the plan's recommended move: not a retraction, but an ADR declaring the freeze **provisional**
  with named 2.0 conditions.

### C2 — Release cadence — CONFIRMED observation, decision owed
- `git for-each-ref` timeline: `v0.16.0` 2026-07-23 14:48, `v1.0.0` 2026-07-23 17:34 — under
  three hours apart, same day. 16 PyPI publishes in the repo's ~7-day tag history.
- With no consumers, a PyPI publish and a git tag are near-substitutes. Set a cadence policy
  (candidate: PyPI on user-visible change *or* a fixed interval, whichever is slower).

### C3 — Provider coverage — CONFIRMED via recorded run; live re-run BLOCKED
- `docs/experiments/gate-divergence.md` Results table records the post-freeze **2026-07-23**
  four-machine suite: **1.0 agreement per machine** (15/15 within-machine pairs each), 24/24
  runs `done`, zero gate errors, deepseek + openai ×3. Per-machine signatures recorded.
- **Coarse-routing critique is pre-addressed:** the suite already carries a deliberately
  contestable machine (`sentiment_borderline`, "genuinely contestable" gates) plus a
  control-flow-critical `severity_escalate` and a `grounding_repair` loop. The recorded note —
  *"free-text outputs diverge on the contestable machines while routing stays identical"* — is
  precisely the reassurance the plan asked for: agreement is not measured only on easy cases.
- **Anthropic priced:** billing-blocked, not key-blocked (SPEC §, README, experiment doc all
  say so). One four-machine × 3-repeat Anthropic pass is ~12 small synthetic runs ≈ **~30k
  tokens, well under \$1**. The decision to leave it blocked is therefore a credit-purchase
  choice, not a cost-at-scale one.

### C4 — Bus factor 1 — CONFIRMED, no action now
- `git shortlog -sne`: 124 + 54 (one human), 8 Claude, 2 dependabot, 2 github-actions.
- Not a defect pre-adoption. The ADR trail (27) + conformance suite already do most of the
  onboarding work; confirm CONTRIBUTING closes the loop.

### D1 — Distribution is the binding constraint — BLOCKED (external)
- Un-testable from inside the repository by design. Internal facts are consistent with the
  claim (mature engineering: 27 ADRs, 91.81% cov, 5-platform matrix; zero external signal on a
  5–7-day-old repo), but the claim's *own* falsifier is external: show two demos to five
  people, record their first verbatim question, count how many understand it unaided, and
  whether ≥1 installs. That test is cheap and owed; it cannot be run here.

---

## Decisions still owed (J-class — must be recorded as ADRs, not defaulted)

Per the plan's Method rule, no J-item enters a fix backlog until its decision is recorded.

1. **C1** — provisional-freeze ADR: what 1.0.0 bought at zero users (Q1), the ADR-0026 cost of
   a needed language change (Q2), and whether 0.17.0-then-1.0.0-on-first-external-issue was the
   honest alternative (Q4). Decide *after* B1's magnitude and D1 are in hand — the plan
   sequences C1 last for this reason.
2. **C2** — cadence policy in CONTRIBUTING.
3. **C4** — acknowledge in CONTRIBUTING; no code.

## Derived fix backlog (T/M-class — verdict-driven)

Items marked **DONE** were fixed on this branch alongside the report.

| From | Action | Size | Status |
|---|---|---|---|
| A1 | Reformat `tests/test_truncation.py` (**DONE**); add `ruff format --check` to `quality.yml` lint step (**CI edit pending** — see below). | XS | **DONE (file) / CI pending** |
| A2 | Fix stale `fail_under = 88` → `90` in CONTRIBUTING (2×); note the `--extra mcp` requirement. (Canonical command already documented; that was the real residual.) | S | **DONE** |
| A3 | Enforce the tag↔CHANGELOG invariant (cut at 0.5.3) in `tests/test_release.py` (**DONE**); `fetch-depth: 0` on the test-job checkout so CI sees tags (**CI edit pending**). The test skips (not fails) without tags, so it is safe already. | S | **DONE (test) / CI pending** |
| B3 | One-line MCP no-persist note in SECURITY.md (ADR-decided). | XS | **DONE** |
| A4 | (Optional) refactor only `cmd_doctor` (CC 41). Do **not** split `cli.py` wholesale. | S | Open (optional) |
| B1 | Freeze the authoring corpus + hand-written acceptance scenarios; run the blind_spot experiment. | L | Blocked (provider key) |
| C3 | (When credited) run one Anthropic four-machine pass (~30k tok) to close the three-provider gap. | XS | Blocked (credit) |
| D1 | Run the five-reader comprehension test; record verbatim first questions. | M | Blocked (external) |

### CI edits pending (need `workflows` permission)

The automation account that produced this branch cannot modify
`.github/workflows/`, so two one-line CI enforcements are prepared here for a
maintainer to apply. Both are additive; the underlying defects (drifted file,
missing test) are already fixed on this branch.

**A1 — gate the format check** (`.github/workflows/quality.yml`, `checks` job,
right after the `Lint` step):

```yaml
      - name: Format check
        run: uv run --extra dev ruff format --check src tests scripts
```

**A3 — let CI see tags** (`.github/workflows/quality.yml`, `test` job checkout
— without it, `test_changelog_entries_from_distribution_cutoff_are_tagged`
skips in CI instead of enforcing):

```yaml
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
          fetch-depth: 0   # pull tags so the tag/CHANGELOG invariant is enforced
```

---

## 5. Assumptions revisited (plan §5)

- **"The weakness is in distribution and the authoring loop, not code quality."** Partly
  supported: code quality is *good* (the audit's own A/C hygiene items are minor; A4 downgrades
  to cosmetic). B1's blind-spot magnitude — the one thing that would confirm the authoring-loop
  weakness — is **un-run here**, so the load-bearing claim of the audit remains *plausible but
  unmeasured*. Do not treat B1 as settled until the corpus experiment runs.
- **"`blind_spot` is measurable with hand-written acceptance criteria."** Untested — the
  experiment did not run. If writing those criteria proves ambiguous, that ambiguity is the
  more interesting finding, exactly as the plan anticipates.
- **Severity ordering (B1, D1 above all).** Survives this pass on structure but not on
  evidence: both top items are the two that could not be executed here. The next session's
  first priority is a provider key and five external readers — not more in-repo ratcheting.
