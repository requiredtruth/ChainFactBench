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

