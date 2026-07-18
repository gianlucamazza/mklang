# Architecture Decision Records

Each ADR records one decision in Context / Decision / Consequences form; the
change checklist in CONTRIBUTING says when to add one.

| ADR                                             | Title                                                                     | Status                                 |
| ----------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------- |
| [0001](0001-capability-tiers.md)                | Capability tiers, not model names                                         | Accepted                               |
| [0002](0002-fanout-llm-reducer.md)              | Fan-out reduces via an LLM state, not built-in aggregators                | Accepted                               |
| [0003](0003-provider-agnostic.md)               | Provider-agnostic: no provider/model pinning in a `.mk`                   | Accepted                               |
| [0004](0004-llm-as-runtime-gates.md)            | LLM as runtime; gates as the reliability mechanism                        | Accepted                               |
| [0005](0005-reasoning-first-class.md)           | Reasoning is first-class and traced                                       | Accepted                               |
| [0006](0006-code-hook-gates.md)                 | Code-hook gates alongside LLM-judged gates                                | Accepted                               |
| [0007](0007-resumable-checkpoints.md)           | Resumable runs via loop-top checkpoints                                   | Accepted                               |
| [0008](0008-hitl-escalate-suspend.md)           | Human-in-the-loop: escalate gates that suspend                            | Accepted                               |
| [0009](0009-conformance-suite.md)               | Conformance suite as the language contract                                | Accepted                               |
| [0010](0010-llm-assisted-lint.md)               | LLM-assisted lint (`mklang lint --llm`)                                   | Accepted                               |
| [0011](0011-mcp-server-surface.md)              | An MCP server surface: machines as commissioned sub-tasks                 | Accepted                               |
| [0012](0012-machine-stdlib.md)                  | A stdlib of general-purpose architecture machines                         | Accepted                               |
| [0013](0013-mcp-surface-completion.md)          | MCP surface completion: discovery, check, durable resume                  | Accepted                               |
| [0014](0014-structured-list-outputs.md)         | Structured list outputs: `parse: list` and raw input resolution           | Accepted                               |
| [0015](0015-console-surface.md)                 | `mklang console`: an agent-first operational TUI whose brain is a machine | Accepted (M1–M3 shipped)               |
| [0016](0016-host-web-search-tool.md)            | Host web-search tool: optional real binding, offline stub default         | Accepted (tools block deferred)        |
| [0017](0017-context-content-management.md)      | Context & content management: host budgets first, language zones later    | Accepted (Layer 0–1; Layer 2 deferred) |
| [0018](0018-output-truncation-anti-cutoff.md)   | Output truncation detection and host recovery policies                    | Accepted (continue deferred)           |
| [0019](0019-mcp-live-events.md)                 | Live engine events on the MCP transport                                   | Accepted                               |
| [0020](0020-host-tool-stub-architecture.md)     | Host tool stub architecture                                               | Accepted                               |
| [0021](0021-filesystem-layout-local-install.md) | Filesystem layout, config resolution, and local installation              | Accepted (phases 1–3 shipped)          |
| [0022](0022-cli-console-experience.md)          | Human-first CLI presentation and responsive console workspace             | Accepted                               |
| [0023](0023-global-local-config-separation.md)  | Global vs local configuration separation                                  | Accepted                               |
