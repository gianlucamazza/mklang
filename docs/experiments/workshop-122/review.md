# Claim review and handover — pending Docs approval

Internal review aid for #122, checked 2026-10-29. This is not a Docs APPROVE decision.

| Abstract claim | Evidence or status | Wording constraint |
| --- | --- | --- |
| Declarative machines, validation, gates and suspension | [SPEC](../../../SPEC.md), [source](../../../src/mklang), [conformance](../../../conformance/README.md), [tests](../../../tests) | Implementation/contract description, not a semantic correctness theorem. |
| Host owns credentials/effects/recovery | [Language boundary](../../what-mklang-is.md); [platform decisions](https://github.com/gianlucamazza/mklang-platform/tree/main/docs/adr) | Do not attribute platform orchestration or production capabilities to the language. |
| Proposed evaluation protocol | [Gate experiment](../gate-divergence.md); exact commands and protocol are in the historical evidence receipt below | Future protocol, not a completed multi-provider result. |
| Small exploratory single-provider run | [Historical 2026-10-29 evidence](../../../evidence/deepseek-2026-10-29) with [metric/protocol correction](../../../evidence/deepseek-2026-10-29/corrected-metrics.json) at commit `1819c20d6e9b4eab49da45b3fa0ccd52c55a3981` | Synthetic and small; no numeric accuracy claim in the abstract. Model alias/revision limitations and unknown historical judge settings remain explicit in the receipt. The corrected blind-spot comparison uses scored base runs only. |
| Lexical support differs from truth | [Platform research evidence](https://github.com/gianlucamazza/mklang-platform/pull/240) | Escalation is not success; a lexical predicate is not a factual oracle. |
| ADR 0037 | [ADR directory](../../adr) | Proposed host mapping only; no shipped Jev or Choice-as-judge claim. |
| Independent reader study | [#61](https://github.com/gianlucamazza/mklang/issues/61), pending | No fabricated readers, acceptance, completion times or feedback. |
| Matched live study | [#60](https://github.com/gianlucamazza/mklang/issues/60), [platform #236](https://github.com/gianlucamazza/mklang-platform/issues/236), incomplete | DeepSeek-only authorization cannot establish cross-provider stability; no replay/live pooling. |

## Review checklist

- Verify the implementation descriptions against the selected release and cite the
  exact version in the eventual paper. Do not upgrade a proposed ADR to a fact.
- Confirm that the contribution is a language/control contract and protocol, with
  empirical limits visible beside every model claim.
- Decide whether the synthetic exploratory receipt belongs in the eventual paper;
  do not backfill missing historical drafts, response revisions or latency.
- For an anonymous venue, prepare a separately approved anonymous artifact package;
  these internal GitHub links are deliberately not an anonymous submission package.
- Confirm three separate decisions: Docs APPROVE on claims, Gianluca's venue choice,
  and Gianluca's yes to actual submission. None is inferred from drafting or CI.

The historical #121 pack and its unpublished-source guards are unchanged. This
folder is under internal `docs/experiments/`; `scripts/build-docs.sh` does not copy it
to the public site. No submission or contact with venue organizers has occurred.
