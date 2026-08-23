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

## `check()` surface (sdist, not the git tree)

`check()` runs the offline suite against the **extracted PyPI sdist**, not a
git checkout:

```sh
cd "mklang-$pkgver"
PYTHONPATH=src python -m pytest tests -q
```

The sdist deliberately excludes `packaging/` (and other release artifacts) —
see `tool.hatch.build.targets.sdist.exclude` in `pyproject.toml`. Repo-hygiene
tests that open those paths (e.g. `test_pkgbuild_version_is_synchronized`)
**must skip** when the file is absent, never crash. The same rule already
applies to git-tag invariants on shallow/sdist trees.

CI enforces this: after `uv build`, the quality gate extracts the sdist and
re-runs the offline suite there. That gate is the load-bearing guard for this
surface — a green full-checkout suite alone does **not** prove AUR `check()`
will pass.

## Release checklist

On every mklang release:

1. Bump `pkgver`, reset `pkgrel=1` (sha256 may still point at the previous
   sdist until step 3).
2. Publish the GitHub Release (`v<version>`) so Trusted Publishing ships the
   sdist to PyPI.
3. Update `source` + `sha256sums` from
   `https://pypi.org/pypi/mklang/<version>/json`. Prefer the
   **content-addressed** `files.pythonhosted.org/packages/<hash>/…` URL from
   the JSON `urls[]` entry for the sdist: the legacy
   `packages/source/m/mklang/mklang-$pkgver.tar.gz` path can 404 for a while
   after publish. Verify the digest against a local download.
4. Push `PKGBUILD` + regenerated `.SRCINFO` to the AUR (see above). AUR lag
   after a PyPI fix is user-visible breakage, not optional polish.
