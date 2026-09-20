#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || { echo "Run ./install.sh first." >&2; exit 1; }
cd "$ROOT"
"$PY" -m compileall -q chainfactbench tests project_gui.py
exec "$PY" -m unittest discover -s tests -v
