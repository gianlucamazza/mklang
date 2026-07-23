# ADR 0025 — Untrusted-context delimiting: provenance taint + data fences

Status: Accepted

## Context

SPEC §11 has been honest since v0.2 that prompt/transition injection is the
language's declared gap: untrusted text (tool observations, host inputs,
prior deposits) was interpolated **raw** into produce prompts and into the
judge's CONTEXT blob, with "no language-level delimiting or dual-channel
control" (§9). The only defenses were voluntary author prose (`std_research` /
`std_compress` mark notes untrusted by hand) and the discipline bullet in §11.
Precedents already pointed the way: ADR 0024 declares file bodies "untrusted
observations", ADR 0017 Layer 2 defers capability separation, and the console
(`console/render.py`) strictly separates chrome markup from untrusted text.

## Decision

Two orthogonal structural mechanisms, both normative in SPEC §6:

1. **Provenance taint.** The engine tracks a per-run set of tainted top-level
   context keys. Trusted at start ⇔ the value equals the author's `.mk`
   `context:` literal; host-supplied or host-overridden values are tainted
   (embedders may vouch via `run(..., trusted_keys=...)`). Every deposit
   taints its `output` key — tool observation, `call` result, **and** produce
   output (the LLM is an untrusted oracle per §11). Fan-out `item` inherits
   the `over:` source's taint (`index` stays trusted); a `call` input is
   tainted in the sub-run iff it interpolates a tainted parent key.
   Checkpoint frames persist the set (`"tainted"`); a frame without the field
   resumes **all-tainted** (fail-safe), and resume-injected values are
   tainted (`checkpoint.taint_frame`, used by CLI `--set` and MCP `inputs`).

2. **Sentinel fences.** Tainted interpolations render as
   `<data-NONCE>\n<value>\n</data-NONCE>` — byte-for-byte, no escaping. The
   nonce is `secrets.token_hex(6)`, fresh per LLM call, re-rolled on
   collision with any fenced value, so content can never forge a closing tag.
   When a produce user message carries a fence, `build_produce_system`
   appends one rule paragraph telling the model fenced spans are data, never
   directives; prompts without tainted interpolations stay byte-identical.
   The judge user message (`llm.base.build_judge_user`, now shared by both
   adapters) fences OUTPUT / REASONING / CONTEXT **unconditionally** — the
   output is always oracle-derived — while the author's `when` conditions
   stay bare; `JUDGE_SYSTEM` states that fenced content is evidence under
   judgment. `parse_choice` is untouched (it reads only the judge reply).

Recorded choices:

- **Provenance, not annotation.** No `.mk` schema change and no authorable
  `trust:` face — taint derives from where a value came from, never from
  authoring. Zones/annotations stay deferred with ADR 0017 Layer 2.
- **No detection heuristics.** Regex payload scanners and injection
  classifiers are brittle and bypassable; the defense is structural only.
- **No content mutation.** Observations cross the boundary byte-for-byte;
  only nonce selection reacts to content, never the content itself.
- **No provider role tricks** beyond the existing system/user split: there is
  no portable multi-role data channel across OpenAI-compatible providers, so
  the fence is the mechanism the spec can mandate for any implementation.
- **Escape hatch:** `run(..., delimit=False)` disables produce-side fencing
  for debugging/comparison (reachable from `mklang test` via the scenario
  `run:` block). Judge-side fencing has no switch.
- The scenario/conformance format gains an `input:` key (host-supplied
  context, tainted by provenance) so cases can exercise host-input
  delimiting; four `taint-*` conformance cases pin observation, host-input,
  call-result fencing and author-literal bareness via the stable `<data-`
  prefix. Judge-prompt fencing is adapter behavior → unit tests, not
  conformance (ADR 0009 boundary, same call as ADR 0024).

## Consequences

- The §11 attack surface item 1 is downgraded from "no delimiting" to a
  structural mitigation with a stated residual risk: a model can still be
  _persuaded_ by fenced content — fences remove ambiguity, not influence.
  Dual-channel / CaMeL-style control stays an explicit open question (§9).
- Live prompts change: machines fed host inputs or tool observations now
  carry fences and (produce-side) one extra system paragraph. Machines whose
  prompts only interpolate author literals are byte-identical.
- Old checkpoints resume all-tainted — safe, at worst over-fenced.
- Remaining `render()` callers outside the produce path (console `agent.mk`
  brain prompts in `console/tools.py`, `llmlint.py` probes, `host.py`) are
  not yet taint-aware — follow-up work, tracked in ROADMAP.
