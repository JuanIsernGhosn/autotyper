#!/bin/sh
# Records docs/demo.gif from the live dry run. Needs: brew install asciinema agg
set -eu
cd "$(dirname "$0")/.."
mkdir -p docs
asciinema rec --overwrite --cols 80 --rows 8 \
  -c "uv run autotyper examples/demo.txt --dry-run --live --seed 7 --error-rate 0.08 --cps 9 --no-default-profile" \
  docs/demo.cast
agg --font-size 16 --theme monokai docs/demo.cast docs/demo.gif
rm docs/demo.cast
echo "wrote docs/demo.gif"
