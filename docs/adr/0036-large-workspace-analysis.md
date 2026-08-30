# ADR 0036 — Metadata index for large workspace analysis

## Context

The console can inspect a workspace through bounded listing, search, and file
reads. A large repository cannot be injected into a single model prompt, while
repeating full directory walks for every question increases latency and makes
coverage difficult to audit. An inventory must also preserve the existing
read-only and sensitive-path policy.

## Decision

The console maintains a versioned, persistent, metadata-only index per
canonical workspace root under the user state directory. The index records
relative path, size, modification time, and a language label inferred from the
extension. It contains no file bodies, secrets, binary contents, or model
output.

The index is rebuilt incrementally when metadata changes and invalidated when
the root or manifest version changes. Existing workspace policy remains the
authority: hidden, build, vendor, cache, sensitive, and escaping paths are not
indexed. File reads and searches remain bounded and live; the index only
narrows candidates and does not replace reading evidence.

Every inspection result exposes coverage metadata. The console evidence brief
and inspector must distinguish indexed files from files actually read, and must
surface truncation or skipped content instead of implying complete analysis.

## Consequences

- Large repositories get a reusable structural inventory and faster candidate
  selection without adding language-specific parser dependencies.
- Persistent state improves latency but is metadata about local workspace
  paths; it is stored in the user state area and can be invalidated safely.
- The approach is intentionally language-agnostic: it does not provide an AST,
  dependency graph, semantic index, embeddings, or a guarantee of whole-repo
  comprehension.
- Coverage is auditable, but analysis quality still depends on the model's
  selection strategy, available token budget, and files actually read.
