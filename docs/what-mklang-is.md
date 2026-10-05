# What mklang is (and is not)

## What mklang is

mklang is an open **declarative language** for LLM-driven state machines. A `.mkl` document is the program: **states produce**, and **gates** decide what happens next (advance, repair, escalate, fail, or call a host tool). The host supplies the interpreter, optional tools, and optional **code-hook** gates for exact rules. The topology is explicit and traceable; prose-gate accuracy and cross-provider stability are **empirical**, not guaranteed ([SPEC](../SPEC.md), [ADR 0004](./adr/0004-llm-as-runtime-gates.md)).

Untrusted context is delimited with provenance and data fences ([ADR 0025](./adr/0025-untrusted-context-delimiting.md)). Exact checks (amounts, dates, allowlists) belong on `hook:` gates ([ADR 0006](./adr/0006-code-hook-gates.md)), not on prose alone.

## What mklang is not

- Not a chat application, and not a substitute for writing application code when you need arbitrary host logic.
- Not a guarantee that every prose gate will be judged correctly; accuracy must be measured on your corpus.
- Not “System One,” and not the same product as TypeSafe Jev. mklang is a **language and host contract** for control flow; Jev (when used at all) is an optional **decision model** behind the existing `judge:` configuration — a different layer.
- Not a claim that any third-party System One model is the default mklang judge.

## Optional host judge (ADR 0037 — Proposed)

[ADR 0037](./adr/0037-jev-noul-host-judge.md) remains **Proposed**. An opt-in Noul-only host adapter can sit behind the existing `judge:` key when set to `jev-*` (`jev-latest` or a pinned id): the host walks gate conditions in order and fires the first Noul at or above a threshold (default 0.5). That is not the default judge (omit `judge:` and judging still follows each state's tier), not a produce tier, and **not production-ready until Path B** bars are measured on a labeled receipt. Choice as `judge:` mapping stays **STOP**. The language SPEC and `.mkl` surface are unchanged; exact rules stay on `hook:`.

Any measured accuracy or latency numbers comparing judges belong in a labeled experiment receipt — not in ADR 0037 alone, and not as TypeSafe marketing restated as ours. See [Jev Noul judge](./guides/jev-noul-judge.md).
