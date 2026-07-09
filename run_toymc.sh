#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
REQUIREMENTS_FILE="$ROOT_DIR/requirements.txt"
STAMP_FILE="$VENV_DIR/.requirements.stamp"

if [[ ! -x "$PYTHON_BIN" ]]; then
  python3 -m venv "$VENV_DIR"
fi

if [[ ! -f "$STAMP_FILE" ]] || ! cmp -s "$REQUIREMENTS_FILE" "$STAMP_FILE"; then
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PIP_BIN" install -r "$REQUIREMENTS_FILE"
  cp "$REQUIREMENTS_FILE" "$STAMP_FILE"
fi

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/run_toymc.py" "$@"
