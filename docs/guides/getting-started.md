# Getting started

One linear path from zero to a first run: install, initialize, set a key, open
the console. Every step is optional to revisit later — nothing here overwrites
anything.

## 1. Install

mklang needs Python ≥ 3.11. The recommended install is [pipx](https://pipx.pypa.io/)
with the console and MCP extras:

```bash
pipx install 'mklang[console,mcp]'
mklang --version
```

Alternatives:

- **pip in a virtualenv** — `pip install 'mklang[console,mcp]'`.
- **install script** — [`scripts/install.sh`](../../scripts/install.sh) runs the
  pipx install plus the initialization below in one go (and has `--uninstall`).
- **Arch Linux** — an AUR-style recipe lives in
  [`packaging/arch/`](https://github.com/gianlucamazza/mklang/tree/main/packaging/arch).

The extras: `[console]` is the interactive TUI, `[mcp]` the MCP server for
agent hosts. Both are optional, but the console is the native surface — take it.

## 2. Initialize your user host

```bash
mklang init --user
```

This scaffolds the XDG user host, never overwriting existing files:

| What                                                | Where                             |
| --------------------------------------------------- | --------------------------------- |
| runtime config, its schema, + `.env`                | `~/.config/mklang/`               |
| your machines, incl. a scaffolded `hello.mk` sample | `~/.local/share/mklang/machines/` |
| console sessions, checkpoints                       | `~/.local/state/mklang/`          |

(Inside a project directory, plain `mklang init` scaffolds the same layout
locally. Full layout and precedence rules: [Installation](./install.md).)

## 3. Set a provider API key

The default config maps mklang's capability tiers to DeepSeek. Edit
`~/.config/mklang/.env` and set:

```bash
DEEPSEEK_API_KEY=sk-...
```

Any other provider works too — set its key and flip `active:` in
`~/.config/mklang/runtime.yaml` (anthropic, openai, google, openrouter, xai,
mistral, or a keyless `local` endpoint such as Ollama). If a key is missing,
the CLI tells you upfront which variable to set instead of failing mid-run.

## 4. First run: the console

The console TUI is where mklang lives — an agent (itself a machine) that
authors, picks, and commissions machines for you, streaming the run
state-by-state:

```bash
mklang console
```

![The mklang console](../assets/demos/console.gif)

Try typing:

- `run the hello machine with task "explain what a state machine is"`
- `write me a machine that triages a support ticket, then test it`

Escalations and tool-consent prompts come back to you inline. Everything about
the console — sessions, `--continue`, swapping the brain with `--agent` — is in
the [Console guide](./console.md).

## No API key yet? Run the deterministic tests

`mklang test` runs a machine against scripted scenarios — no provider, no key,
fully deterministic. The scaffolded sample ships with its own script:

```bash
mklang test ~/.local/share/mklang/machines/hello.mk \
  --script ~/.local/share/mklang/machines/hello.test.yaml
# PASS accepted-first-try
# PASS repair-fires-then-accepted
```

Open `hello.mk` next to it — it is a readable, commented tour of the language's
signature move: a generative state whose exit is decided by an LLM-judged prose
gate, with a bounded repair loop.

## Next steps

- **Check your setup at any time:** `mklang doctor` — which config file and
  layer won, which `.env` files loaded, key status per provider, machine roots.
- **Run stdlib machines by name, no file needed:**
  `mklang run std_self_consistency --set task="What is the capital of Australia?"`
  — see the [machine stdlib](../reference/stdlib.md).
- **Shell completions:** `eval "$(register-python-argcomplete mklang)"` (needs
  the `[completions]` extra; per-shell details in [Installation](./install.md)).
- **Commission machines from Claude Code / MCP hosts:**
  `claude mcp add mklang -- mklang-mcp` — the server resolves config and keys
  from your user host.
- **Write your own machine:** the [cheatsheet](../reference/cheatsheet.md) and
  the [Authoring guide](./authoring.md), with the
  [CLI reference](../reference/cli.md) for every command and exit code.
