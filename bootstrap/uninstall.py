#!/usr/bin/env python3
"""Safely remove only artifacts owned by a recorded bootstrap installation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from common import (
    PLUGIN_ENTRY,
    PLUGIN_NAME,
    PLUGIN_SELECTOR,
    atomic_write,
    load_marketplace,
    managed_targets,
    marketplace_bytes,
    path_digest,
)


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args()

    home = args.home.resolve()
    codex_home = (args.codex_home or home / ".codex").resolve()
    state_path = home / ".local" / "state" / "codex-exosphere" / "install-state.json"
    if not state_path.is_file():
        raise RuntimeError(f"Install state not found: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("version") != 1:
        raise RuntimeError(f"Unsupported install state version: {state.get('version')!r}")

    allowed_paths = {
        target.destination.resolve() for target in managed_targets(home, codex_home)
    }
    allowed_paths.add((codex_home / "config.toml").resolve())
    created = [(Path(item["path"]), item["digest"]) for item in state.get("created", [])]
    unexpected = [path for path, _ in created if path.resolve() not in allowed_paths]
    if unexpected:
        raise RuntimeError(f"Refusing unexpected path in install state: {unexpected[0]}")
    if state.get("plugin_selector", PLUGIN_SELECTOR) != PLUGIN_SELECTOR:
        raise RuntimeError("Refusing unexpected plugin selector in install state")
    for path, expected in created:
        if not path.exists() or path_digest(path) != expected:
            raise RuntimeError(f"Refusing to remove changed or missing managed path: {path}")

    marketplace_path = home / ".agents" / "plugins" / "marketplace.json"
    marketplace = None
    if state.get("marketplace_entry_added"):
        marketplace, _ = load_marketplace(marketplace_path)
        matches = [item for item in marketplace["plugins"] if item.get("name") == PLUGIN_NAME]
        if matches != [PLUGIN_ENTRY]:
            raise RuntimeError("Refusing to remove changed or missing marketplace entry")

    print(f"REMOVE   recorded paths: {len(created)}")
    print(f"REMOVE   plugin: {bool(state.get('plugin_installed'))}")
    print(f"UPDATE   marketplace: {bool(state.get('marketplace_entry_added'))}")
    if not args.apply:
        print("plan only: pass --apply to uninstall")
        return 0

    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["CODEX_HOME"] = str(codex_home)
    if state.get("plugin_installed"):
        subprocess.run(
            ["codex", "plugin", "remove", state.get("plugin_selector", PLUGIN_SELECTOR)],
            check=True,
            env=environment,
        )
    if marketplace is not None:
        marketplace["plugins"] = [
            item for item in marketplace["plugins"] if item.get("name") != PLUGIN_NAME
        ]
        if state.get("marketplace_file_created") and not marketplace["plugins"]:
            marketplace_path.unlink()
        else:
            atomic_write(marketplace_path, marketplace_bytes(marketplace))
    for path, _ in reversed(created):
        remove_path(path)
    state_path.unlink()
    print("uninstalled managed artifacts")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
