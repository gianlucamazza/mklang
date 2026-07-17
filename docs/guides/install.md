# Local installation and host layout

Install the desired surfaces, then initialize either a project or your user host:

```bash
pip install 'mklang[console,mcp]'
mklang init --user
# or, inside a project
mklang init
```

`init` never overwrites existing files. Project mode creates `config/runtime.yaml`,
`config/runtime.schema.json`, `machines/`, and `.env`. User mode uses XDG roots:

| Data | Default |
| --- | --- |
| runtime config and `.env` | `~/.config/mklang/` |
| user machines | `~/.local/share/mklang/machines/` |
| console sessions/checkpoints | `~/.local/state/mklang/` |

`XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_STATE_HOME` are honored. Tests and
sandboxes can use `MKLANG_CONFIG_DIR`, `MKLANG_DATA_DIR`, and `MKLANG_STATE_DIR`.
An explicit `--config` wins, followed by `MKLANG_CONFIG`, project config, user
config, system config, and finally the read-only bundled example.

Machine precedence is stdlib → plugins → system → user → project. Use
`mklang machines` to see the winning source.
