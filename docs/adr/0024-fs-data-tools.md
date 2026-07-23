# ADR 0024 — Filesystem data tools with a coding-tool workspace model

Status: Accepted

## Context

Machines had no way to touch the filesystem: the only side-effect seam is the
`tool:` state, and the builtins covered search, KB, and mail. BP §13 already
reserved a "class 3" slot for machine data I/O (read a CSV, write a report):
host tools under a confined root, relative paths only, ADR 0020 envelopes,
file bodies treated as untrusted observations.

Two open questions remained. Where does the code live — the ROADMAP sketched
"plugins", while every other reference I/O tool is a core builtin with a stub
default. And how is the root configured — the requirement was to mirror how
native coding agents (Claude Code, Codex) manage workspaces and projects:
launch in a directory and that directory is the workspace; explicit overrides
form a precedence chain; reads are free within the workspace; writes need an
explicit grant in headless surfaces.

## Decision

1. **Core builtins, one module.** `list_files`, `read_file`, `write_file` live
   in `mklang.fs`, mirroring `search.py`/`kb.py`: `FSBackend` protocol,
   `StubFSBackend` (offline refusal) / `LocalFSBackend` (real disk,
   `stub: false`), `configure_fs()`, env tier selection, `tool_obs` envelopes.
   Registered in `BUILTINS`. No in-memory fake tier: unlike search/mail there
   is no network or side effect to simulate — tests sandbox the real backend
   with a temporary directory.

2. **Coding-tool workspace resolution** (most specific wins):

   | Layer    | Mechanism                                                       |
   | -------- | --------------------------------------------------------------- |
   | explicit | `--workspace` on `mklang run` / `mklang-mcp`; `configure_fs()`  |
   | env      | `MKLANG_FS_ROOT` (layers per ADR 0023: env > project > user)    |
   | default  | the process **cwd** — like launching a coding agent in a folder |

   `MKLANG_FS_BACKEND=stub|none|off` forces offline anywhere (CI, tests —
   the pytest suite pins it in `conftest.py`). A `tools:` block in
   `runtime.yaml` stays deferred with ADR 0016; when it lands, env keeps
   overriding it per the existing precedence rules.

3. **Reads live by default; writes grant-gated.** This deliberately amends the
   ADR 0020 stub-by-default posture for fs _reads_: running a machine from a
   directory is the same deliberate act as opening a coding agent there.
   Writes to real disk additionally require `--allow-write` /
   `MKLANG_FS_WRITE=1` / `mklang.fs.allow_writes(True)`. The console grants
   writes through its existing one-time per-session tool consent (SPEC §11);
   the MCP root is fixed by the operator at server startup, never per call.

4. **Confinement and write policy.** Relative paths only; `..`, absolute
   paths, and dotfile segments are refused lexically; the final path is
   `resolve()`d and must stay `is_relative_to` the resolved root (the console
   `_workspace_path` pattern), and the **resolved** target is re-checked
   against the dotfile policy — a visible symlink cannot smuggle in `.env` or
   a target outside the root, and `list` omits such children. Writes: suffix
   allowlist of data formats (**no `.mkl`** — that stays with the console's
   `write_machine`), no delete tool, overwrite only with `overwrite: true`,
   byte caps on read and write, atomic unique-tempfile+`os.replace` writes at
   mode 0600 (the checkpoint precedent),
   audit line at INFO (tool, relative path, byte count — never contents).
   TOCTOU races between check and open are out of scope, as for the console
   workspace. File bodies are untrusted observations (SPEC §11).

## Comparison with native coding tools (audited July 2026)

Write gating matches current practice: Claude Code denies edits by default in
headless mode, Codex `exec` defaults to a read-only sandbox, Grok prompts on
writes — our headless grant (`--allow-write`) is the same posture. On **reads**
we are deliberately stricter than all three: in their standard modes Claude
Code reads system-wide minus user deny rules (no built-in `.env` deny), Codex
`workspace-write` reads system-wide, and Grok auto-approves reads everywhere
(read confinement only in its `strict` profile). Those tools can afford broad
reads because a human sits in a per-operation approval loop; a machine run is
unattended, so we pick the most restrictive boundary that still does the job
(least-privilege). The dotfile ban is the counterpart of Codex's protected
paths (`.git`, `.codex`, `.agents` stay read-only even in writable roots) and
stronger than Claude Code's default.

Deferred until a real use case appears, recorded in the ROADMAP: multiple
roots (the `--add-dir` / `writable_roots` analog — embedding hosts already get
this via `configure_fs`) and per-path allow/deny rules (the `Read(...)` /
`Edit(...)` syntax now shared by Claude Code and Grok).

## Consequences

- A machine can read its project's data and write reports with zero setup:
  `cd project && mklang run report.mkl -- --allow-write`. Confinement, not
  ceremony, is the safety boundary — write gating matches coding-agent
  practice, read confinement is deliberately stricter (see the comparison
  above).
- The offline test suite stays hermetic (stub pinned in `conftest.py`), and
  `mklang doctor` shows the resolved workspace and write grant.
- Anything outside the workspace root is unreachable by construction; hosts
  needing multiple roots bind their own backend via `configure_fs`.
- The dotfile ban plus workspace confinement reproduces the coding-tool split
  between agent-facing project memory (non-dotted workspace files, readable)
  and host state (checkpoints, sessions, `.env` — unreachable); the mapping is
  documented in BP §13 "Memory & planning mapping". Append semantics for
  durable memory files stays deferred until a real use case appears
  (read → `overwrite: true` covers it within the caps).
- No conformance cases: this is host-tool behavior, not language semantics
  (ADR 0009 boundary).
