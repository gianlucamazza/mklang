# Local installation and host layout

First time? Follow [Getting started](./getting-started.md) — this page is the
host-layout and config-resolution reference.

Install the desired surfaces, then initialize either a project or your user host:

```bash
pip install 'mklang[console,mcp]'
mklang init --user
# or, inside a project
mklang init
```

`pipx install 'mklang[console,mcp]'` is equivalent and keeps the CLI in its own
environment; [`scripts/install.sh`](../../scripts/install.sh) does both steps in
one go (idempotent, `--extras` to customize, `--uninstall` to remove the package
while listing the user data it leaves behind).

`init` never overwrites existing files. Project mode creates `config/runtime.yaml`,
`config/runtime.schema.json`, `machines/` (with a commented `hello.mk` sample and
its `hello.test.yaml` scenario script), and `.env`. User mode uses XDG roots:

| Data                                        | Default                           |
| ------------------------------------------- | --------------------------------- |
| runtime config and `.env`                   | `~/.config/mklang/`               |
| user machines (incl. the `hello.mk` sample) | `~/.local/share/mklang/machines/` |
| console sessions/checkpoints                | `~/.local/state/mklang/`          |

`XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_STATE_HOME` are honored. Tests and
sandboxes can use `MKLANG_CONFIG_DIR`, `MKLANG_DATA_DIR`, and `MKLANG_STATE_DIR`.
An explicit `--config` wins, followed by `MKLANG_CONFIG`, project config, user
config, system config, and finally the read-only bundled example — the same
chain for the CLI, the console, and `mklang-mcp`. `.env` layers per key:
real environment > project `.env` > user `.env` (ADR 0023).

Machine precedence is stdlib → plugins → system → user → project. Use
`mklang machines` to see the winning source, and `mklang doctor` to see every
resolved layer (config, env, keys, machine roots, state paths) at once.

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
