#!/usr/bin/env bash
# Install mklang for the current user via pipx (ADR 0021 phase 3).
#
#   curl -fsSL https://raw.githubusercontent.com/gianlucamazza/mklang/main/scripts/install.sh | bash
#   ./scripts/install.sh [--extras console,mcp] [--force] [--uninstall]
#
# Installs the PyPI package with the console and MCP extras, then scaffolds the
# XDG user host (config, .env, sample machine) with `mklang init --user`.
# Never touches system paths and never overwrites existing user files.

set -euo pipefail

EXTRAS="mcp"  # the console ships in the core package since 0.15.0
FORCE=0
UNINSTALL=0

usage() {
	sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
	case "$1" in
	--extras)
		EXTRAS="${2:?--extras needs a value, e.g. console,mcp}"
		shift 2
		;;
	--force)
		FORCE=1
		shift
		;;
	--uninstall)
		UNINSTALL=1
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		echo "unknown option: $1" >&2
		usage >&2
		exit 2
		;;
	esac
done

need_pipx() {
	if command -v pipx >/dev/null 2>&1; then
		return
	fi
	echo "pipx is required but not on PATH. Install it first:" >&2
	echo "  Arch Linux:    sudo pacman -S python-pipx" >&2
	echo "  Debian/Ubuntu: sudo apt install pipx" >&2
	echo "  anywhere:      python3 -m pip install --user pipx && python3 -m pipx ensurepath" >&2
	exit 2
}

if [ "$UNINSTALL" = 1 ]; then
	need_pipx
	pipx uninstall mklang
	config_dir="${MKLANG_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/mklang}"
	data_dir="${MKLANG_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mklang}"
	state_dir="${MKLANG_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/mklang}"
	echo "Uninstalled. User data was left in place; remove it yourself if wanted:"
	for dir in "$config_dir" "$data_dir" "$state_dir"; do
		[ -d "$dir" ] && echo "  $dir"
	done
	exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
	echo "python3 is required but not on PATH." >&2
	exit 2
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
	echo "mklang needs Python >= 3.11; found $(python3 --version)." >&2
	exit 2
fi

need_pipx

if pipx list --short 2>/dev/null | grep -q '^mklang ' && [ "$FORCE" = 0 ]; then
	echo "mklang is already installed via pipx — run \`pipx upgrade mklang\` to update,"
	echo "or re-run this script with --force to reinstall."
	exit 0
fi

if [ "$FORCE" = 1 ]; then
	pipx install --force "mklang[$EXTRAS]"
else
	pipx install "mklang[$EXTRAS]"
fi

# A freshly configured pipx bin dir may not be on PATH in this shell yet.
mklang_bin="$(command -v mklang || true)"
if [ -z "$mklang_bin" ]; then
	pipx_bin_dir="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"
	mklang_bin="$pipx_bin_dir/mklang"
fi
if [ ! -x "$mklang_bin" ]; then
	echo "mklang was installed but its binary is not on PATH — run \`pipx ensurepath\`," >&2
	echo "open a new shell, then run \`mklang init --user\` yourself." >&2
	exit 2
fi

"$mklang_bin" init --user

if ! command -v mklang >/dev/null 2>&1; then
	echo "note: $(dirname "$mklang_bin") is not on PATH yet — run \`pipx ensurepath\` and open a new shell."
fi

config_dir="${MKLANG_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/mklang}"
data_dir="${MKLANG_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mklang}"
cat <<EOF

mklang is installed. Next steps:
  1. Set a provider API key:  edit $config_dir/.env  (DEEPSEEK_API_KEY by default)
  2. Open the console TUI:    mklang console
  3. Or try it without a key (scripted, deterministic):
       mklang test $data_dir/machines/hello.mk \\
         --script $data_dir/machines/hello.test.yaml

Docs: https://gianlucamazza.github.io/mklang/getting-started/
EOF
