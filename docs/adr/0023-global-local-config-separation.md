# ADR 0023 — Global vs local configuration separation

Status: Accepted

## Context

ADR 0021 gave mklang its XDG layout and a clean first-hit-wins config chain,
but four surfaces still broke the separation between the **global** host
(user/system roots) and the **local** project:

- A project `.env` shadowed the user `.env` entirely (`elif` in
  `config.load_provider`): a project defining only `DEEPSEEK_API_KEY` hid an
  `ANTHROPIC_API_KEY` that lived in the user host.
- `mklang-mcp` pinned `config/runtime.example.yaml` as its default `--config` —
  a checkout-relative path passed as _explicit_, which short-circuits
  `resolve_config`. Spawned outside a checkout (how MCP clients launch it), the
  server never found the user host despite the docs claiming it would.
- The console workspace defaulted to `./machines` unconditionally, even when no
  such directory existed — authored machines never landed in the user machines
  root that `init --user` seeds.
- `--hitl` refused to run without an explicit `--checkpoint`, although the ADR
  0021 table names the state root as the home of checkpoints.

There was also no way to _see_ which layer won: setup failures surfaced only at
run time, one at a time.

## Decision

1. **One resolution principle: local wins per surface, global fills the gaps.**

   | Surface        | Local (project)              | Global (user/system)                  | Semantics                             |
   | -------------- | ---------------------------- | ------------------------------------- | ------------------------------------- |
   | `runtime.yaml` | `./config/runtime.yaml`      | user config root, `/etc/mklang`       | first hit wins (whole file)           |
   | `.env`         | nearest `.env` up from cwd   | `<config root>/.env`                  | **per key**: project wins, user fills |
   | machines       | `./machines` / `--dir`       | user machines, `/usr/share/mklang`    | later layer wins per machine name     |
   | checkpoints    | explicit `--checkpoint` path | `<state root>/checkpoints/` (default) | explicit wins                         |

   `runtime.yaml` stays first-hit-wins on purpose: a run is governed by exactly
   one config file, never a deep merge of several. `.env` is the one per-key
   surface because keys are independent secrets, not one document.

2. **Every entry point uses the same chain.** `mklang-mcp`'s default `--config`
   becomes `None`, flowing through `resolve_config` exactly like the CLI
   (explicit → `$MKLANG_CONFIG` → project → user → `/etc` → bundled).
   `resolve_config_with_layer` names the winning layer for diagnostics.

3. **The console workspace follows the local-then-global rule:** `./machines`
   when present, else the user machines root. An explicit `--workspace` always
   wins.

4. **`--hitl` without `--checkpoint` suspends into
   `<state root>/checkpoints/<machine>-<stamp>-<uuid>.json`** instead of
   erroring; the suspension message prints the path, `mklang resume` takes it
   from there.

5. **`mklang init --user` reaches parity with project init**: it also copies
   `runtime.schema.json` next to `runtime.yaml`, so the example's
   yaml-language-server header validates in both locations.

6. **`mklang doctor` makes the separation observable**: resolved config path
   and winning layer, which `.env` files loaded, per-provider key status
   (active-provider gaps are errors, `local` is exempt like the run-time key
   gate), machine roots with counts, and the state paths. Exit 1 when the
   active provider cannot run.

## Consequences

- A host configured once with `mklang init --user` now behaves identically for
  the CLI, the console, and the MCP server, from any directory.
- Project overrides stay possible everywhere without hiding the global host:
  dropping a one-line `.env` into a project no longer disables every other
  provider key.
- Tests must isolate the user host (`MKLANG_CONFIG_DIR` / `MKLANG_DATA_DIR` /
  `MKLANG_STATE_DIR`) — a developer's real `~/.config/mklang` must never leak
  into assertions. The suites were hardened accordingly.
- `mklang-mcp` clients can drop the manual `--config /abs/path` workaround.
