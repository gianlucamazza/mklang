# ADR 0012 — A stdlib of general-purpose architecture machines

Status: Accepted

## Context

The reasoning architectures mklang claims as its idiom (README "Reasoning
architectures", SPEC §10 cookbook) existed only as domain-specific demos in
`examples/` — support tickets, expense policies, quiz questions. A host that
wanted "self-consistency over MY task" had to copy a demo and rewrite its prose.
The architectures were documentation; they were not _callable_.

Three verified engine facts bound what a reusable machine library can be:

- `call:` and `tool:` names are **static** — never interpolated. A library
  machine cannot take "which worker to call" or "which tool to use" as a
  parameter; only `input:` _values_ pass through `render()`.
- `render()` always stringifies, so **lists do not survive a `call: input:`
  boundary**; real lists reach a machine's context only via CLI `--set` (JSON)
  or MCP `inputs` (direct merge).
- Generative output is always text, so a planner state cannot produce the list
  an `over:` needs — **Plan-and-Execute is not implementable** as a single
  machine today.

SPEC §4.8 defines only "a registry of machines"; how the registry is populated
is host-side, not normative. Conformance cases build their registries inline
(`scripttest.build_registry`) and never touch discovery.

## Decision

Ship a **bundled stdlib of purely generative, parameterized architecture
machines** under `src/mklang/data/stdlib/` (wheel force-include, mirroring the
bundled schema), loaded via `importlib.resources` with a repo-tree fallback.
Seven machines, uniform contract — input `task` (string), result `answer`,
machine name = filename = `std_*`:

`std_cot`, `std_self_consistency`, `std_refine`, `std_tot`, `std_debate`,
`std_map_reduce`, `std_cascade`.

Excluded on the constraints above, deliberately: ReAct (host tools), Router-of-
experts (static `call:` + domain categories), exact-policy gates (host hooks),
Plan-and-Execute (needs structured list output — a `[maybe]` ROADMAP note).
These remain documented patterns, not machines.

- **Registry precedence, user always wins:** every host registry is layered
  `stdlib ← entry-point plugins ← directory siblings ← run target`. A sibling
  or target that reuses a stdlib name shadows it and the host surfaces a
  warning. The language is untouched (0.2); the schema is untouched.
- **Run-by-name:** a machine argument that is not an existing file but matches
  a base-registry name resolves to that machine — `mklang run std_cot --set
task="…"` and MCP `run(path="std_cot")` with no server change. A run-by-name
  checkpoint records `machine_sha256: null` (nothing to pin; the machine is
  versioned with the package) and `verify_hash` accepts it.
- **Inline MCP sources can `call: std_*`** — `prepare_source` seeds its registry
  with the base registry instead of the bare target.
- **Third-party machines** join via a new `mklang.machines` entry-point group
  (a machine document dict, or a zero-arg factory returning one), mirroring the
  existing `mklang.tools` / `mklang.hooks` groups.
- **Validation is CI's job:** registry loading stays lax (a malformed sibling
  or plugin is skipped with a warning), so the test suite pins every stdlib
  machine — schema-valid, zero semantic errors _and warnings_, zero lint
  findings — and runs each machine's bundled `*.test.yaml` scenarios through
  the scripted harness. Conformance is untouched.

## Consequences

- Every documented architecture that _can_ be a machine now ships as one:
  callable from user machines (`call: std_refine`), runnable by name from CLI
  and MCP, parameterized by context — the demos in `examples/` become
  illustrations, not the only way in.
- The precedence rule makes the stdlib safe to inject everywhere: users can
  never be broken by a stdlib name, only warned when they shadow one.
- List-valued parameters (`items`, `personas`) work from CLI/MCP but not
  through `call: input:` — documented per machine in the catalog
  (docs/reference/stdlib.md). Lifting this needs structured outputs, the same gap that
  blocks Plan-and-Execute.
- The stdlib's quality bar is enforced by tests, not by runtime checks; a
  malformed stdlib file would vanish from the registry silently at runtime but
  cannot pass CI.
