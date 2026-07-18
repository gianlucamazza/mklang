# Arch Linux packaging

An AUR-style `PKGBUILD` for mklang (ADR 0021 phase 3).

## Naming

The package is `mklang`, not `python-mklang`: Arch names a package after the
application when the primary deliverable is a program (cf. `ruff`, `uv`). The
importable Python library is secondary to the `mklang` / `mklang-mcp` CLIs.

## What it installs

- The Python package and the `mklang` / `mklang-mcp` entry points.
- `/etc/mklang/runtime.yaml` — system-level runtime config (lowest precedence
  after project and user configs; listed in `backup=` so local edits survive
  upgrades) plus its JSON schema.
- `/usr/share/mklang/machines/` — the example machines as system machines,
  runnable by name from anywhere (`mklang run triage`).

`python-openai` (hard dependency) and `python-mcp` (optdepend for the MCP
server) live in the AUR, not in the official repos — acceptable for an AUR
package, but they must be built first when installing with plain `makepkg`.

## Build and install locally

```sh
cd packaging/arch
makepkg -si         # build from the PyPI sdist and install
namcap PKGBUILD     # lint the recipe
mklang --version    # smoke test
```

## Publishing to the AUR

The AUR wants its own git repo containing `PKGBUILD` + `.SRCINFO`; `.SRCINFO`
is generated at publish time and deliberately not committed here:

```sh
git clone ssh://aur@aur.archlinux.org/mklang.git aur-mklang
cp PKGBUILD aur-mklang/ && cd aur-mklang
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO && git commit -m "mklang $(source ./PKGBUILD && echo "$pkgver-$pkgrel")" && git push
```

## Release checklist

On every mklang release, bump `pkgver`, reset `pkgrel=1`, and update
`sha256sums` with the new sdist digest from
`https://pypi.org/pypi/mklang/<version>/json`.
