# Host embedding guide

How to run mklang machines from an outer host — scripts, services, MCP clients,
or an orchestrator — without treating the CLI as a black box. This is **host
surface** documentation: it does not add language syntax.

Related: [CLI reference](../reference/cli.md), [Stability](stability.md),
[Best practices](best-practices.md) (§5 tools, §11 security, §14 surfaces),
[SPEC §7](../../SPEC.md) (checkpoints), [SPEC §11](../../SPEC.md) (threat model),
ADRs 0007 (checkpoints), 0008 (HITL), 0011/0013 (MCP), 0018 (truncation),
0019 (live events), 0020 (tool envelopes), 0023 (config layers), 0024 (fs tools).

Wire shape of outcomes:
[`schema/run-result.schema.json`](../../schema/run-result.schema.json).

---

## 1. Entry points (pick one)

| Surface                                    | When to use                            | Commission                                                             |
| ------------------------------------------ | -------------------------------------- | ---------------------------------------------------------------------- |
| **Library** (`mklang.host` + `mklang.run`) | In-process Python host                 | `prepare_path` / `prepare_source` → `engine.run` → `host.build_output` |
| **CLI** `mklang run` / `resume`            | Shell, cron, CI, n8n “Execute Command” | path or registered name; JSON on stdout                                |
| **MCP** `mklang-mcp`                       | Agentic clients                        | tools `run` / `resume`; events as `mklang.event`                       |

All three share the same prepare → run → output seam. Prefer the library when
you already own a Python process; CLI when the host is polyglot; MCP when the
client is an agent runtime.

```text
config + .env  →  prepare (load machine, tools, hooks, LLM)
               →  inject inputs / host defaults (today, now)
               →  engine.run(... suspendable / escalate_suspend / on_truncate)
               →  build_output (+ checkpoint file or MCP handle on suspend)
```

### Minimal library sketch

```python
from mklang import host
from mklang.engine import run

cfg = "config/runtime.yaml"  # or resolve via host paths
p = host.prepare_path(cfg, provider=None, path="machines/hello.mkl")
ctx = dict(p.machine.context)
host.inject_host_defaults(ctx)  # only fills declared empty today/now
# apply user inputs into ctx here (e.g. host.set_path(ctx, "ticket.body", …))
res = run(
    p.machine,
    ctx,
    p.registry,
    p.llm,
    p.prov.tiers,
    tools=p.tools,
    hooks=p.hooks,
    suspendable=False,
    escalate_suspend=False,
    on_truncate="halt",  # or "report"
    # Control-flow taint (SPEC §6 / ADR 0030): refuse an effectful tool reached
    # through a decision a judge made over external data. Default "report".
    on_untrusted_flow="halt",
    tool_effects={"my_plugin_lookup": "read"},  # unclassified tools are effectful
)
out = host.build_output(res)
# out["status"] in {"done", "halt", "suspended"}
```

CLI equivalent:

```bash
mklang run machines/hello.mkl --format json --on-truncate halt --untrusted-flow halt
# exit 0 done | 1 halt | 3 suspended | 2 usage/host error
```

---

## 2. Run outcomes and exit codes

| `status`    | Meaning                                       | CLI exit      | Host action                                                     |
| ----------- | --------------------------------------------- | ------------- | --------------------------------------------------------------- |
| `done`      | Finished; `result` is the machine result      | 0             | Consume `result` / `trace` / `usage`                            |
| `halt`      | Aborted; not resumable from this result alone | 1             | Log `error` (+ `at`); fix inputs/machine; do not invent success |
| `suspended` | Resumable (budget or HITL escalate)           | 3             | Persist `checkpoint`; later `resume`                            |
| `error`     | MCP prepare/validation failure payload        | (tool result) | Fix request; not an engine halt                                 |

Common `error` strings (non-exhaustive): `budget-exhausted`, `escalated`,
`gate-fail`, `output-truncated`, `no-gate-matched`, `untrusted-control-flow`
(only under `on_untrusted_flow="halt"`), `call-failed`, `call-depth-exceeded`,
tool observation failures as judged by fail gates. A halt inside a sub-machine
reaches the caller prefixed — `call-failed: <sub reason>` — so match on the
prefix, not on equality.

**Mapping tip for outer orchestrators:** treat exit 3 / `suspended` as
_waiting_ (human or budget), not as failure. Treat exit 1 / `halt` as failure
unless your product policy retries after changing inputs.

---

## 3. Checkpoints and HITL

### Enabling suspend

| Goal                       | Flags / knobs                                                                              |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| Pause on budget exhaustion | CLI `--checkpoint PATH` or `suspendable=True` + save frames                                |
| Pause on `escalate` gates  | CLI `--hitl` (implies checkpoint; default path under XDG state) or `escalate_suspend=True` |
| Resume                     | `mklang resume CHECKPOINT --set human.reply=…` or MCP `resume` with handle/path            |

Checkpoints are **plaintext JSON** of the blackboard and frames (mode `0600` is
a floor, not encryption). Do **not** put API keys or long-lived secrets in
machine `context:` — they will be snapshotted. See SPEC §11.

### Resume injection

Inject only what the human (or outer workflow) decided, e.g.
`--set human.reply=approve`. Injected paths are **tainted** like other untrusted
context (SPEC §6). Prefer a dedicated key (`human.reply`) over overwriting
business fields.

### MCP handles vs files

- Default MCP suspend returns an opaque **single-use** in-memory handle in
  `checkpoint`.
- Pass `checkpoint_path` for a durable file (cross-process); result may include
  both `checkpoint` (handle) and `checkpoint_file` (path).
- Prefer durable paths for multi-process HITL (dashboard → worker).

---

## 4. Secrets, config, and tools

| Concern                  | Rule                                                                                                 |
| ------------------------ | ---------------------------------------------------------------------------------------------------- |
| Provider API keys        | Host `.env` / environment (`api_key_env` in `runtime.yaml`); never in `.mkl`                         |
| Tool secrets (Tavily, …) | Same layering; `runtime.yaml` `tools:` is non-secret backend selection                               |
| Config resolution        | Explicit `--config` / `MKLANG_CONFIG` > project > user > system > bundled ([install](install.md))    |
| FS workspace             | `--workspace` / `MKLANG_FS_ROOT` / `tools.fs.workspace`; writes need `--allow-write` or config grant |
| Tool plugins             | Entry points `mklang.tools` — host registers callables; machines only name them                      |

Capability policy: a machine may _request_ a tool; only the host _grants_ it.
Unknown third-party tools should default to conservative risk metadata (BP §5.5).

---

## 5. Timeouts, budgets, truncation

| Knob                               | Effect                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------ |
| Machine `budget:`                  | Step/loop guard (fan-out charges branch count)                           |
| CLI `--max-tokens` / `cost_budget` | Shared produce+judge token budget; with checkpoint → suspend; else halt  |
| `--on-truncate report\|halt`       | Produce cutoff (ADR 0018): annotate vs halt `output-truncated`           |
| `--untrusted-flow report\|halt`    | Control-flow taint (ADR 0030): annotate vs halt `untrusted-control-flow` |
| Provider HTTP timeouts             | Adapter/host concern; console implements cooperative cancel + `close()`  |

Production hosts that must not silently ship partial rewrites should use
`--on-truncate halt` (or the library equivalent) and surface `error` clearly.

---

## 6. Wire shape (JSON)

Canonical core fields from `host.build_output(res)`:

```json
{
  "status": "done",
  "error": null,
  "result": "…",
  "usage": { "input_tokens": 0, "output_tokens": 0 },
  "trace": [{ "step": 1, "state": "…", "…": "…" }]
}
```

Surface extensions:

| Field             | CLI                        | MCP                                |
| ----------------- | -------------------------- | ---------------------------------- |
| `at`              | yes when set               | yes when set                       |
| `checkpoint`      | path on suspend            | handle (and path semantics differ) |
| `checkpoint_file` | —                          | durable path when requested        |
| `warnings`        | stderr, not always in JSON | array on result                    |

Validate example payloads against
[`schema/run-result.schema.json`](../../schema/run-result.schema.json).
The schema allows `additionalProperties` so surfaces may grow without a
language bump; pin `schema_version` in your host if you re-emit a stricter
envelope.

---

## 7. Recommended host checklist

- [ ] Resolve config once; fail fast if the provider key env var is missing
- [ ] `check` / `lint` machines in CI before live commission
- [ ] Scenario-test with `mklang test` (scripted LLM) for control flow
- [ ] Decide suspend policy (checkpoint path + HITL) before irreversible tools
- [ ] Map `done` / `suspended` / `halt` to your orchestrator’s success/wait/fail
- [ ] Keep secrets out of blackboard and checkpoint files
- [ ] Prefer `--on-truncate halt` for fidelity-critical pipelines
- [ ] Log `usage` and correlation ids next to the outer job id
- [ ] Treat tool observations and resume injections as untrusted (SPEC §6)

---

## 8. Out of scope (deliberate)

- HTTP webhook server / cron daemon inside the language core
- Built-in WhatsApp / Supabase / Gmail connectors (host plugins only)
- Encrypting checkpoints at rest (host responsibility if required)
- Guaranteeing identical gate traces across providers (measure via
  [gate divergence](../../docs/experiments/gate-divergence.md); do not assume)

For product-level trigger and queue infrastructure, keep an outer orchestrator
and call mklang for **logic** — that is the intended split between host platform
and language runtime.
