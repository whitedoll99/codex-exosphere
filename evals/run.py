#!/usr/bin/env python3
"""Command-line entry point for the evaluation harness."""

from __future__ import annotations

import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from evals.harness import main
else:
    from .harness import main


if __name__ == "__main__":
    sys.exit(main())
