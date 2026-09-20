#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -ne 0 ]; then
    echo "Usage: ./demo.sh" >&2
    exit 2
fi
exec "$ROOT/cli.sh" demo
