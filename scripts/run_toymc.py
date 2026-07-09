"""Thin repo-local wrapper that runs the CLI from this checkout."""

from __future__ import annotations

import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from toymc_cosmic.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
