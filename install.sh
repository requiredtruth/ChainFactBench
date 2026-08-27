#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"

printf 'phase: Python syntax\n'
python -m compileall -q chainfactbench tests
printf 'phase: unit and integration tests\n'
python -m unittest discover -s tests -v
printf 'phase: offline end-to-end demo\n'
python -m chainfactbench demo


# Desktop control-panel dependency. Kept in the project venv.
GUI_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
GUI_VENV="$GUI_ROOT/.venv"
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
[ -x "$GUI_VENV/bin/python" ] || python3 -m venv "$GUI_VENV"
"$GUI_VENV/bin/python" -m pip install --disable-pip-version-check --upgrade PySide6
touch "$GUI_VENV/.repo-gui-ready"
