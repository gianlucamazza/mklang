# ADR 0029 — Internal layout refactor (cli split, console bridge, tests mirror src)

Status: Accepted

## Context

`cli.py` mixed command handlers, the `doctor` diagnostics and the argparse tree
in ~1140 lines; `console/app.py` nested the worker↔UI thread bridge inside a
closure factory; `capabilities.py` sat at the package top level with a single
consumer in `console/`; `tests/` was a flat directory of 50+ modules whose
grouping was not reconstructible by inspection.

ADR 0026 fixes the 1.0 stable surface: the language, the entry-point group
names (`mklang.tools` etc. as strings), the `run(...)` embedding API, the
package-root exports, `data/**` resource anchors, and the documented logger
hierarchy. **Internal module paths are not part of that contract** — "src/mklang
is a conformant reference implementation, not the contract itself".

Deliberately out of scope, and why:

- `engine.py` stays monolithic: `_Runner` is shared mutable state across
  judge/fan-out/taint/budget concerns; splitting it is a semantic refactor with
  conformance risk, not a file move.
- The flat host-tool modules (`fs.py`, `kb.py`, `mail.py`, `search.py`,
  `tools.py`, `tool_obs.py`, `toolconfig.py`) stay put: `mklang.tools:*` are
  entry-point targets, `mklang.fs`/`mklang.kb`/`mklang.search` APIs appear in
  ADR 0016/0020/0024 and the guides, and two of them sit in the mypy strict
  ratchet.

## Decision

- `doctor` diagnostics → `cli_doctor.py`; the argparse tree → `cli_parser.py`
  as `build_parser(handlers)` with injected handlers, so the parser module
  never imports the commands (cycle-free by construction). `cli.py` keeps the
  `mklang.cli:main` entry point, every `cmd_*`, the test patch-points and the
  `"mklang.cli"` logger.
- `TextualBridge` + its `_BridgeApp` protocol → `console/bridge.py`;
  `capabilities.py` → `console/capabilities.py` (console-surface policy).
- `tests/` mirrors the src layout (`engine/ lang/ llm/ console/ mcp/ tools/
host/ conformance/ repo/`) with one root `conftest.py` exposing a `REPO_ROOT`
  anchor. Basenames keep their domain prefixes — the prepend import mode
  requires global uniqueness and there are no `__init__.py` files. `test_live.py`
  stays at the root because the workflows invoke it by path.
- The mypy strict tier stays append-only and untouched: no listed module moved;
  new modules start at the base tier.

## Consequences

- Behavior-neutral: same CLI, same outputs, same test count, same loggers; the
  stable surface of ADR 0026 is unchanged.
- Earlier ADRs cite pre-refactor paths; they are era-accurate records and stay
  as written. The current layout is documented in
  [architecture](../reference/architecture.md).
- Future moves of internal modules follow the same rule: free within the
  boundaries above, with entry-point targets, resource anchors and the strict
  tier updated in the same commit.
