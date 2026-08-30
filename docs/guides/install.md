# Local installation and host layout

First time? Follow [Getting started](./getting-started.md) for the linear
walk-through — this page is the canonical reference for installing, the host
layout, and config resolution; every other page links here instead of
repeating it.

Install the desired surfaces, then initialize either a project or your user host:

```bash
pip install 'mklang[mcp]'  # console TUI included by default
mklang init --user
# or, inside a project
mklang init
```

`pipx install 'mklang[mcp]'` is equivalent and keeps the CLI in its own
environment; [`scripts/install.sh`](../../scripts/install.sh) does both steps in
one go (idempotent, `--extras` to customize, `--uninstall` to remove the package
while listing the user data it leaves behind).

`init` never overwrites existing files. Project mode creates `config/runtime.yaml`,
`config/runtime.schema.json`, `machines/` (with a commented `hello.mkl` sample and
its `hello.test.yaml` scenario script), and `.env`.

## Host layout

This section is the documentation source of truth for host-owned paths — ADR
0021 records the decision and rollout history; the implementation authority is
`mklang.paths`, and changes to it must update this table in the same commit.

| Root   | Location                                                   | Contents                                 |
| ------ | ---------------------------------------------------------- | ---------------------------------------- |
| Config | `$XDG_CONFIG_HOME/mklang` (default `~/.config/mklang`)     | `runtime.yaml`, its schema, `.env`       |
| Data   | `$XDG_DATA_HOME/mklang` (default `~/.local/share/mklang`)  | user `machines/` (incl. the `hello.mkl` sample) |
| State  | `$XDG_STATE_HOME/mklang` (default `~/.local/state/mklang`) | console sessions and checkpoints         |
| System | `/etc/mklang`, `/usr/share/mklang/machines`                | system config and machines               |

Console sessions always live under
`$XDG_STATE_HOME/mklang/console/sessions/<id>/`. `mklang init --user` creates
the user roots and seeds `machines/` with the `hello.mkl` sample plus its
`hello.test.yaml` scenario (keyless first run via `mklang test`).

## Config and machine resolution

An explicit `--config` wins, followed by `MKLANG_CONFIG`, project config, user
config, system config, and finally the read-only bundled example — the same
chain for the CLI, the console, and `mklang-mcp`. `.env` layers per key:
real environment > project `.env` > user `.env` (ADR 0023).

Machine resolution is shared by CLI, console, and path-based MCP runs: the
registry layers stdlib → plugins → system → user → project root → project
`machines/`, with the last matching machine winning. Root-level project `.mkl`
files remain readable for compatibility; new console-authored files go under
`machines/`. A path outside a recognizable project loads only its sibling
machines plus the global registry. Use `mklang machines` to see the winning
source per name, and `mklang doctor` to see every resolved layer (config, env,
keys, machine roots, state paths) at once.

### Environment variables

One reference for every `MKLANG_*` variable the runtime reads:

| Variable                                                     | Effect                                                           |
| ------------------------------------------------------------ | ---------------------------------------------------------------- |
| `MKLANG_CONFIG`                                              | select one runtime config file directly (beats discovery)        |
| `MKLANG_CONFIG_DIR` / `MKLANG_DATA_DIR` / `MKLANG_STATE_DIR` | override the user roots (tests, sandboxes)                       |
| `MKLANG_DEBUG=1`                                             | re-raise unexpected errors with a full traceback                 |
| `MKLANG_SEARCH_BACKEND=stub\|fake\|tavily`                   | bind the `search` tool (unset: Tavily when `TAVILY_API_KEY` set) |
| `MKLANG_KB_BACKEND=stub\|fake`                               | bind the `search_kb` tool                                        |
| `MKLANG_MAIL_BACKEND=fake`                                   | bind the `send_reply` tool                                       |
| `MKLANG_LIVE=1`                                              | opt into the live provider test suite (development only)         |
| `MKLANG_STREAM_CANCEL=cooperative\|immediate`                | console provider-stream cancellation policy (default: immediate) |

Each `MKLANG_*_BACKEND` variable overrides the corresponding `tools.<name>`
binding in `runtime.yaml` (ADR 0016): env var > `tools:` block > default.

Provider API keys are named per provider by `api_key_env` in `runtime.yaml`
(e.g. `DEEPSEEK_API_KEY`) and read from the environment or the layered `.env`
files — never from the config file itself.

OpenAI's current example mapping is `gpt-5.6-luna` (fast), `gpt-5.6-terra`
(balanced), and `gpt-5.6-sol` (reasoning). These are configuration references,
not proof that a specific account has access; verify `/v1/models` before live
use.

## Arch Linux

An AUR-style recipe lives in
[`packaging/arch/`](https://github.com/gianlucamazza/mklang/tree/main/packaging/arch)
(`makepkg -si` from that directory). It installs the system layer of the
precedence chain above: `/etc/mklang/runtime.yaml` (lowest-precedence config,
preserved across upgrades) and `/usr/share/mklang/machines/` (the example
machines as system machines, runnable by name from anywhere).

## Shell completions

Completions are powered by [argcomplete](https://kislyuk.github.io/argcomplete/)
via the `[completions]` extra:

```bash
pip install 'mklang[completions]'   # or: pipx inject mklang argcomplete
```

Then activate for your shell:

```bash
# bash — add to ~/.bashrc
eval "$(register-python-argcomplete mklang)"

# zsh — add to ~/.zshrc (bashcompinit bridges argcomplete)
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete mklang)"

# fish — add to ~/.config/fish/config.fish
register-python-argcomplete --shell fish mklang | source
```

With a pipx install, `register-python-argcomplete` must be on your PATH: either
install argcomplete system-wide (e.g. `pacman -S python-argcomplete`,
`pipx install argcomplete`) or use argcomplete's global activation.
