# ADR 0021 — Filesystem layout, config resolution, and local installation

Status: Accepted (phases 1–3 shipped; the optional MCP user service is deferred)

## Context

`mklang` installs cleanly from PyPI, but the CLI still assumes a repo checkout:
`--config` defaults to the relative path `config/runtime.example.yaml`, console
sessions live in the hardcoded `~/.mklang/console/sessions`, and machines are
resolved only from the bundled stdlib, entry-point plugins, and an explicit
`--dir`. There is no user- or system-level home for config and machines, and no
scaffolding command — a `pip install mklang` outside the repo has nothing to run
against until the user hand-builds a config.

Best practices §13 defines the filesystem taxonomy for _machines_ (host paths,
workspace `.mkl`, data tools); this ADR is the host-side counterpart: where the
host itself keeps config, machines, and state.

## Decision

1. **XDG layout, three roots** (module `mklang/paths.py`):

   | Root   | Path                                                       | Holds                         |
   | ------ | ---------------------------------------------------------- | ----------------------------- |
   | config | `$XDG_CONFIG_HOME/mklang` (default `~/.config/mklang`)     | `runtime.yaml`, `.env`        |
   | data   | `$XDG_DATA_HOME/mklang` (default `~/.local/share/mklang`)  | `machines/`                   |
   | state  | `$XDG_STATE_HOME/mklang` (default `~/.local/state/mklang`) | console sessions, checkpoints |

   System level: `/etc/mklang/runtime.yaml` and `/usr/share/mklang/machines/`.
   Env overrides `MKLANG_CONFIG_DIR` / `MKLANG_DATA_DIR` for tests and sandboxes.

2. **Config resolution order** when `--config` is omitted (first hit wins):
   explicit flag → `$MKLANG_CONFIG` → `./config/runtime.yaml` (project) →
   user config root → `/etc/mklang/runtime.yaml` → bundled example (read-only
   fallback, preserving today's behavior inside the repo).

3. **Machine search path**, later wins, extending `base_registry`'s existing
   layering: stdlib ← entry-point plugins ← system machines ← user machines ←
   project `--dir`. `mklang machines` labels the new sources `system` / `user`
   alongside `stdlib` / `plugin` / `local`.

4. **`mklang init`** scaffolds a project (`config/runtime.yaml`, `machines/`,
   `.env` template); `mklang init --user` seeds the user config root from the
   bundled example, never overwriting existing files.

5. **Legacy migration.** `~/.mklang/console/sessions` keeps working: the state
   root is preferred for new sessions, the legacy path is read if present.

6. **Packaging artifacts** (`packaging/`): a pipx-based `scripts/install.sh`
   (`pipx install 'mklang[console,mcp]'` + `mklang init --user`, with
   `--uninstall`) and an AUR `PKGBUILD` installing the system-level config and
   machines. The optional systemd _user_ unit for the MCP server is deferred
   (see Rollout).

## Consequences

- `pip install mklang && mklang console` works from any directory once
  `mklang init --user` has run — no repo checkout required.
- Precedence is boring and predictable: project beats user beats system beats
  bundled, mirroring the machine-registry layering authors already know.
- The bundled example config stops being the implicit production default;
  inside the repo nothing changes.
- New surface to test: `paths.py` resolution under monkeypatched env, init
  idempotency, and registry labeling of the new sources.

## Rollout

Phases 1–2 shipped: `paths.py`, config resolution, state migration,
`mklang init`, machine search path, and discovery source labels. Phase 3
shipped: `scripts/install.sh` (pipx) and the AUR recipe in `packaging/arch/`.
The optional systemd user unit is deferred: the MCP server is stdio-only —
clients spawn it per session, so a persistent service has nothing to listen
on; it becomes meaningful once the server grows a network transport
(e.g. streamable HTTP).
