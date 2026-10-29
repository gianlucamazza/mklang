# Explicit Control Boundaries for LLM Judgement in Recoverable Workflows

**Claim-reviewed internal Lab draft for #122 — not a submitted paper.**
One-page abstract draft for AGENTVERIFY; venue-specific paper layout is separate.

LLM applications often mix a model's judgement with the code that decides whether
an external action may execute. A plausible model response can then be mistaken
for authorization, and a retry can repeat work whose outcome is unknown. We study
a narrower language boundary: a model may supply judgement and generated data,
while a host retains responsibility for credentials, effects and recovery.

We present mklang, a declarative language for bounded LLM machines. A machine
states its control graph and gate policy explicitly. Deterministic loading and
validation reject malformed declarations; the runtime applies the declared gates,
step and repair budgets and suspension semantics. Model variability remains observable
within that boundary. A suspended machine returns state to its host rather than
silently acquiring authority to execute an external operation. Host adapters must
preserve the distinction between a result, an escalation and permission to act.

The proposed contribution is an inspectable control contract and a reproducible
failure-oriented evaluation protocol. Language conformance and host recovery are
separate subjects. We exercise malformed graphs, explicit branch policies, bounded
repair, external-data control flow and suspend/resume behavior using deterministic
fixtures. A complementary live protocol records all attempted model decisions,
including failures and escalations, with dataset, code and configuration identities.
It compares declared gate behavior and output stability without treating repeated
items as independent tasks. Model quality, authorization correctness and recovery
correctness are reported separately.

Available artifacts include the language implementation, conformance tests and a
small synthetic single-provider exploratory run. Those observations motivate the
protocol; they do not establish general accuracy, successful task completion,
cross-provider equivalence or deployment safety. A matched multi-provider study,
independent readers and stronger task-level success oracles remain future work.
The current research-report verifier measures a declared lexical support predicate,
which is not factual correctness. Unknown external effects require host-side
reconciliation rather than an implicit model-driven retry.

We do not claim state-of-the-art LLM accuracy. We do not claim Choice as a `judge:`
mapping, or that Jev replaces mklang gates. ADR 0037 describes a **Proposed host
mapping**, not a shipped Jev product. We invite discussion of the boundary's
expressiveness, failure modes and evaluation design, and of the evidence needed
before such a component can support stronger reliability claims.
