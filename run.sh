#!/bin/sh

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

if [ -f "venv/bin/activate" ]; then
    . "venv/bin/activate"
    exec python main.py "$@"
fi

exec python3 main.py "$@"
