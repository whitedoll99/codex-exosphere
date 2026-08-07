#!/usr/bin/env python3
"""Render a host-specific Codex config from portable repository inputs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from common import atomic_write, render_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", type=Path, required=True, help="Host-local TOML input")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--output", type=Path, help="Output path; omit to print to stdout")
    parser.add_argument("--force", action="store_true", help="Replace a different output file")
    args = parser.parse_args()

    content = render_config(args.local, args.home.resolve())
    if args.output is None:
        sys.stdout.buffer.write(content)
        return 0
    output = args.output.resolve()
    if output.exists() and output.read_bytes() != content and not args.force:
        raise RuntimeError(f"Refusing to overwrite different config: {output}")
    atomic_write(output, content)
    print(f"rendered: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
