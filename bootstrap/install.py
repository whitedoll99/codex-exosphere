#!/usr/bin/env python3
"""Plan or apply a non-overwriting installation of this Codex environment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from common import (
    PLUGIN_SELECTOR,
    add_marketplace_entry,
    atomic_write,
    copy_missing,
    forbidden_repository_content,
    forbidden_repository_paths,
    load_marketplace,
    managed_targets,
    marketplace_bytes,
    marketplace_status,
    path_digest,
    paths_equal,
    render_config,
)


STATE_VERSION = 1


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def command_environment(home: Path, codex_home: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["CODEX_HOME"] = str(codex_home)
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the planned changes")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--local-config", type=Path, help="Render and install config.toml")
    parser.add_argument("--skip-plugin-add", action="store_true")
    args = parser.parse_args()

    home = args.home.resolve()
    codex_home = (args.codex_home or home / ".codex").resolve()
    state_path = home / ".local" / "state" / "codex-exosphere" / "install-state.json"
    marketplace_path = home / ".agents" / "plugins" / "marketplace.json"

    forbidden = forbidden_repository_paths()
    if forbidden:
        rendered = ", ".join(str(path) for path in forbidden)
        raise RuntimeError(f"Refusing repository with forbidden sensitive paths: {rendered}")
    forbidden_content = forbidden_repository_content()
    if forbidden_content:
        rendered = ", ".join(f"{path} ({label})" for path, label in forbidden_content)
        raise RuntimeError(f"Refusing repository with credential-like content: {rendered}")
    if state_path.exists():
        raise RuntimeError(f"Install state already exists; verify or uninstall first: {state_path}")

    targets = managed_targets(home, codex_home)
    plan: list[tuple[str, str, Path]] = []
    conflicts: list[Path] = []
    for target in targets:
        if not target.destination.exists():
            plan.append(("CREATE", target.label, target.destination))
        elif paths_equal(target.source, target.destination):
            plan.append(("SAME", target.label, target.destination))
        else:
            plan.append(("CONFLICT", target.label, target.destination))
            conflicts.append(target.destination)

    rendered_config: bytes | None = None
    config_path = codex_home / "config.toml"
    if args.local_config:
        rendered_config = render_config(args.local_config.resolve(), home)
        if not config_path.exists():
            plan.append(("CREATE", "rendered Codex config", config_path))
        elif config_path.read_bytes() == rendered_config:
            plan.append(("SAME", "rendered Codex config", config_path))
        else:
            plan.append(("CONFLICT", "rendered Codex config", config_path))
            conflicts.append(config_path)

    marketplace, original_marketplace = load_marketplace(marketplace_path)
    entry_status = marketplace_status(marketplace)
    if entry_status == "missing":
        plan.append(("UPDATE", "personal marketplace", marketplace_path))
    elif entry_status == "same":
        plan.append(("SAME", "personal marketplace", marketplace_path))
    else:
        plan.append(("CONFLICT", "personal marketplace", marketplace_path))
        conflicts.append(marketplace_path)

    for action, label, path in plan:
        print(f"{action:8} {label}: {path}")
    if conflicts:
        raise RuntimeError("Refusing installation because destination conflicts exist")
    if not args.apply:
        print("plan only: pass --apply to change the target environment")
        return 0

    created: list[Path] = []
    marketplace_added = False
    plugin_installed = False
    try:
        for target in targets:
            if not target.destination.exists():
                copy_missing(target.source, target.destination)
                created.append(target.destination)
        if rendered_config is not None and not config_path.exists():
            atomic_write(config_path, rendered_config)
            created.append(config_path)
        if entry_status == "missing":
            atomic_write(
                marketplace_path,
                marketplace_bytes(add_marketplace_entry(marketplace)),
            )
            marketplace_added = True
        if not args.skip_plugin_add:
            subprocess.run(
                ["codex", "plugin", "add", PLUGIN_SELECTOR],
                check=True,
                env=command_environment(home, codex_home),
            )
            plugin_installed = True

        state: dict[str, Any] = {
            "version": STATE_VERSION,
            "created": [
                {"path": str(path), "digest": path_digest(path)} for path in created
            ],
            "marketplace_entry_added": marketplace_added,
            "marketplace_file_created": marketplace_added and original_marketplace is None,
            "plugin_installed": plugin_installed,
            "plugin_selector": PLUGIN_SELECTOR,
        }
        atomic_write(state_path, (json.dumps(state, indent=2) + "\n").encode())
    except Exception:
        if plugin_installed:
            subprocess.run(
                ["codex", "plugin", "remove", PLUGIN_SELECTOR],
                check=False,
                env=command_environment(home, codex_home),
            )
        if marketplace_added:
            if original_marketplace is None:
                marketplace_path.unlink(missing_ok=True)
            else:
                atomic_write(marketplace_path, original_marketplace)
        for path in reversed(created):
            remove_path(path)
        raise

    print(f"installed; state: {state_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
