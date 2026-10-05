# What mklang is (and is not)

## What mklang is

mklang is an open **declarative language** for LLM-driven state machines. A `.mkl` document is the program: **states produce**, and **gates** decide what happens next (advance, repair, escalate, fail, or call a host tool). The host supplies the interpreter, optional tools, and optional **code-hook** gates for exact rules. The topology is explicit and traceable; prose-gate accuracy and cross-provider stability are **empirical**, not guaranteed ([SPEC](../SPEC.md), [ADR 0004](./adr/0004-llm-as-runtime-gates.md)).

Untrusted context is delimited with provenance and data fences ([ADR 0025](./adr/0025-untrusted-context-delimiting.md)). Exact checks (amounts, dates, allowlists) belong on `hook:` gates ([ADR 0006](./adr/0006-code-hook-gates.md)), not on prose alone.

## What mklang is not

- Not a chat application, and not a substitute for writing application code when you need arbitrary host logic.
- Not a guarantee that every prose gate will be judged correctly; accuracy must be measured on your corpus.
- Not “System One,” and not the same product as TypeSafe Jev. mklang is a **language and host contract** for control flow; Jev (when used at all) would be an optional **decision model** behind the existing `judge:` configuration — a different layer.
- Not a claim that any third-party System One model ships as the default mklang judge today.

## Optional future host judge (ADR 0037 — Proposed only)

A **Proposed** architecture decision ([ADR 0037](./adr/0037-jev-noul-host-judge.md), merge `ac8ea61d`) records intent for a **Noul-only** host-side mapping under `judge:`: the host walks gate conditions in order and fires the first answer at or above a threshold. That ADR does **not** ship an adapter, does **not** change the language SPEC, and does **not** authorize Choice as a `judge:` mapping (that path is rejected). Implementation remains blocked until an explicit EXPLORE sì and Path B acceptance bars.

Any measured accuracy or latency numbers comparing judges belong in a labeled experiment receipt — not in ADR 0037 alone, and not as TypeSafe marketing restated as ours.
