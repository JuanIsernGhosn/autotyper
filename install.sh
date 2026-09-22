#!/bin/sh
# Installs autotyper as a uv tool. Sets up uv first if it is missing.
set -eu

REPO="https://github.com/JuanIsernGhosn/autotyper"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "autotyper only supports macOS." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found, installing it..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

uv tool install --force "git+$REPO"

echo
echo "Installed. Try:  autotyper --help"
echo "If the command is not found, run:  uv tool update-shell  and open a new terminal."
