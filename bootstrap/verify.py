#!/usr/bin/env python3
"""Verify repository safety, plugin structure, and optional installed state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from common import (
    PLUGIN_NAME,
    MARKETPLACE_NAME,
    REPO_ROOT,
    deployed_plugin_base_version,
    forbidden_repository_content,
    forbidden_repository_paths,
    load_marketplace,
    load_plugin_manifest,
    managed_targets,
    marketplace_status,
    paths_equal,
    plugin_paths_equal,
    plugin_versions_match,
    render_config,
)


SKILLS = {
    "systematic-diagnosis",
    "verification-before-reporting",
    "review-feedback-triage",
    "review-packet-preparation",
    "bounded-tdd",
    "problem-framing",
    "contract-design",
    "architecture-quality-analysis",
    "domain-model-audit",
    "interface-boundary-audit",
    "resident-continuity",
}


def check(condition: bool, message: str, failures: list[str]) -> None:
    if condition:
        print(f"OK   {message}")
    else:
        print(f"FAIL {message}")
        failures.append(message)


PLUGIN_DIAGNOSTICS = (
    "installed plugin canonical semantics match",
    "installed plugin deployment version is valid",
    "installed plugin effective selection is unique",
    "installed plugin selected cache matches deployment",
)


def load_json_without_duplicate_keys(payload: str) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate JSON key: {key}")
            document[key] = value
        return document

    return json.loads(payload, object_pairs_hook=reject_duplicate_keys)


def selected_plugin_cache(
    home: Path,
    codex_home: Path,
    deployed: Path,
    deployed_version: object,
) -> Path | None:
    """Resolve the one managed plugin cache entry from Codex's JSON output.

    This deliberately does not enumerate or choose among cache directories.
    The Codex-selected installed version is the only cache path considered.
    """
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["CODEX_HOME"] = str(codex_home)
    try:
        result = subprocess.run(
            ["codex", "plugin", "list", "--marketplace", MARKETPLACE_NAME, "--json"],
            check=False,
            env=environment,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return None
        document = load_json_without_duplicate_keys(result.stdout)
        if not isinstance(document, dict) or set(document) != {"installed", "available"}:
            return None
        installed = document["installed"]
        available = document["available"]
        if not isinstance(installed, list) or not isinstance(available, list):
            return None
        if any(
            not valid_plugin_list_entry(entry, expected_installed=True)
            for entry in installed
        ) or any(
            not valid_plugin_list_entry(entry, expected_installed=False)
            for entry in available
        ):
            return None
        candidates = [
            entry
            for entry in installed
            if isinstance(entry, dict)
            and (
                entry.get("pluginId") == f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
                or (
                    entry.get("name") == PLUGIN_NAME
                    and entry.get("marketplaceName") == MARKETPLACE_NAME
                )
            )
        ]
        if len(candidates) != 1:
            return None
        entry = candidates[0]
        allowed_keys = {
            "pluginId",
            "name",
            "marketplaceName",
            "version",
            "installed",
            "enabled",
            "source",
            "marketplaceSource",
            "installPolicy",
            "authPolicy",
        }
        if not set(entry).issubset(allowed_keys):
            return None
        required = {
            "pluginId",
            "name",
            "marketplaceName",
            "version",
            "installed",
            "enabled",
            "source",
            "installPolicy",
            "authPolicy",
        }
        if not required.issubset(entry):
            return None
        if (
            entry["pluginId"] != f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
            or entry["name"] != PLUGIN_NAME
            or entry["marketplaceName"] != MARKETPLACE_NAME
            or entry["version"] != deployed_version
            or entry["installed"] is not True
            or entry["enabled"] is not True
            or not isinstance(entry["version"], str)
            or not isinstance(entry["installPolicy"], str)
            or not isinstance(entry["authPolicy"], str)
        ):
            return None
        marketplace_source = entry.get("marketplaceSource")
        if marketplace_source is not None and (
            not isinstance(marketplace_source, dict)
            or set(marketplace_source) != {"sourceType", "source"}
            or not isinstance(marketplace_source["sourceType"], str)
            or not isinstance(marketplace_source["source"], str)
        ):
            return None
        source = entry["source"]
        if (
            not isinstance(source, dict)
            or set(source) != {"source", "path"}
            or source["source"] != "local"
            or not isinstance(source["path"], str)
            or not Path(source["path"]).is_absolute()
            or Path(source["path"]).resolve(strict=True)
            != deployed.resolve(strict=True)
        ):
            return None
        try:
            deployed_plugin_base_version(entry["version"])
        except (ValueError, TypeError):
            return None
        cache = (
            codex_home
            / "plugins"
            / "cache"
            / MARKETPLACE_NAME
            / PLUGIN_NAME
            / entry["version"]
        )
        cache_parents = [
            codex_home / "plugins",
            codex_home / "plugins" / "cache",
            codex_home / "plugins" / "cache" / MARKETPLACE_NAME,
            codex_home / "plugins" / "cache" / MARKETPLACE_NAME / PLUGIN_NAME,
        ]
        if any(path.is_symlink() for path in cache_parents) or not cache.is_dir() or cache.is_symlink():
            return None
        return cache
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return None


def valid_plugin_list_entry(entry: object, *, expected_installed: bool) -> bool:
    if not isinstance(entry, dict):
        return False
    allowed_keys = {
        "pluginId",
        "name",
        "marketplaceName",
        "version",
        "installed",
        "enabled",
        "source",
        "marketplaceSource",
        "installPolicy",
        "authPolicy",
    }
    required = allowed_keys - {"marketplaceSource"}
    if not required.issubset(entry) or not set(entry).issubset(allowed_keys):
        return False
    if (
        not all(isinstance(entry[key], str) for key in ("pluginId", "name", "marketplaceName", "installPolicy", "authPolicy"))
        or (entry["version"] is not None and not isinstance(entry["version"], str))
        or entry["installed"] is not expected_installed
        or not isinstance(entry["enabled"], bool)
    ):
        return False
    source = entry["source"]
    if not isinstance(source, dict) or not isinstance(source.get("source"), str):
        return False
    source_kind = source["source"]
    source_shapes = {
        "local": {"source", "path"},
        "git": {"source", "url", "ref", "sha"},
        "git-subdir": {"source", "url", "path", "ref", "sha"},
        "npm": {"source", "package", "version", "registry"},
    }
    if source_kind not in source_shapes:
        return False
    required_source_keys = {
        "local": {"source", "path"},
        "git": {"source", "url"},
        "git-subdir": {"source", "url", "path"},
        "npm": {"source", "package"},
    }[source_kind]
    if not required_source_keys.issubset(source) or not set(source).issubset(source_shapes[source_kind]):
        return False
    if not all(isinstance(source[key], str) for key in required_source_keys):
        return False
    if any(
        key in source and source[key] is not None and not isinstance(source[key], str)
        for key in source_shapes[source_kind] - required_source_keys
    ):
        return False
    marketplace_source = entry.get("marketplaceSource")
    return marketplace_source is None or (
        isinstance(marketplace_source, dict)
        and set(marketplace_source) == {"sourceType", "source"}
        and isinstance(marketplace_source["sourceType"], str)
        and isinstance(marketplace_source["source"], str)
    )


def verify_installed_plugin(
    home: Path,
    codex_home: Path,
    source: Path,
    deployed: Path,
    failures: list[str],
) -> None:
    check(
        plugin_paths_equal(source, deployed, ignore_manifest_version=True),
        PLUGIN_DIAGNOSTICS[0],
        failures,
    )
    check(plugin_versions_match(source, deployed), PLUGIN_DIAGNOSTICS[1], failures)

    try:
        deployed_version = load_plugin_manifest(deployed).get("version")
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        deployed_version = None
    cache = selected_plugin_cache(home, codex_home, deployed, deployed_version)
    check(cache is not None, PLUGIN_DIAGNOSTICS[2], failures)
    check(
        cache is not None and plugin_paths_equal(deployed, cache),
        PLUGIN_DIAGNOSTICS[3],
        failures,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args()
    failures: list[str] = []

    required = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "config" / "AGENTS.md",
        REPO_ROOT / "agents" / "luna_worker.toml",
        REPO_ROOT / "agents" / "terra_reviewer.toml",
        REPO_ROOT / "bin" / "run-luna-worker",
        REPO_ROOT / "bin" / "luna-packet-guard",
        REPO_ROOT / "bin" / "codex-observe",
        REPO_ROOT / "bin" / "codex-observe-shim",
        REPO_ROOT / "codex_observability" / "model.py",
        REPO_ROOT / "codex_observability" / "store.py",
        REPO_ROOT / "codex_observability" / "web.py",
        REPO_ROOT / "codex_observability" / "static" / "index.html",
        REPO_ROOT / "codex_observability" / "schema" / "event-v1.schema.json",
        REPO_ROOT / "plugins" / PLUGIN_NAME / ".codex-plugin" / "plugin.json",
    ]
    check(all(path.exists() for path in required), "required repository files exist", failures)
    check(not forbidden_repository_paths(), "no forbidden sensitive filenames", failures)
    check(not forbidden_repository_content(), "no credential-like content", failures)
    base_config = (REPO_ROOT / "config" / "config.base.toml").read_text()
    base_shape_ok = all(
        marker in base_config
        for marker in (
            'approval_policy = "never"',
            'sandbox_mode = "workspace-write"',
            '[plugins."resident-engineering-patterns@personal"]',
        )
    )
    check(base_shape_ok, "base config contains required portable settings", failures)
    try:
        example = render_config(
            REPO_ROOT / "config" / "local.example.toml", Path("/portable/example")
        ).decode()
        example_ok = (
            "/portable/example/codex-exosphere" in example
            and "/home/" not in example
        )
        check(example_ok, "example local config renders without VM-specific paths", failures)
    except RuntimeError:
        check(False, "example local config renders without VM-specific paths", failures)
    try:
        json.loads(
            (REPO_ROOT / "plugins" / PLUGIN_NAME / ".codex-plugin" / "plugin.json").read_text()
        )
        check(True, "plugin manifest parses as JSON", failures)
    except (OSError, UnicodeError, json.JSONDecodeError):
        check(False, "plugin manifest parses as JSON", failures)

    skill_root = REPO_ROOT / "plugins" / PLUGIN_NAME / "skills"
    found_skills = {path.name for path in skill_root.iterdir() if path.is_dir()}
    check(found_skills == SKILLS, "exactly the expected eleven skills are present", failures)
    policies_ok = all(
        "allow_implicit_invocation: true"
        in (skill_root / skill / "agents" / "openai.yaml").read_text()
        for skill in SKILLS
    )
    check(policies_ok, "all eleven skills allow implicit invocation", failures)
    launcher = REPO_ROOT / "bin" / "run-luna-worker"
    shell = subprocess.run(["bash", "-n", str(launcher)], check=False)
    check(shell.returncode == 0, "Luna launcher passes bash -n", failures)
    guard = REPO_ROOT / "bin" / "luna-packet-guard"
    guard_compile = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; compile(Path(__import__('sys').argv[1]).read_text(), __import__('sys').argv[1], 'exec')",
            str(guard),
        ],
        check=False,
    )
    check(guard_compile.returncode == 0, "Luna packet guard compiles", failures)
    check(bool(guard.stat().st_mode & 0o111), "Luna packet guard is executable", failures)
    observe = REPO_ROOT / "bin" / "codex-observe"
    check(bool(observe.stat().st_mode & 0o111), "Codex observability CLI is executable", failures)
    observe_shim = REPO_ROOT / "bin" / "codex-observe-shim"
    shim_shell = subprocess.run(["sh", "-n", str(observe_shim)], check=False)
    check(shim_shell.returncode == 0, "Codex observability PATH shim passes sh -n", failures)
    check(bool(observe_shim.stat().st_mode & 0o111), "Codex observability PATH shim is executable", failures)
    observability_sources = sorted((REPO_ROOT / "codex_observability").glob("*.py"))
    observability_compile = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import sys; "
                "[compile(Path(p).read_text(), p, 'exec') for p in sys.argv[1:]]"
            ),
            *map(str, observability_sources),
        ],
        check=False,
    )
    check(observability_compile.returncode == 0, "observability Python sources compile", failures)
    launcher_text = launcher.read_text()
    for skill in ("bounded-tdd", "systematic-diagnosis", "verification-before-reporting"):
        check(skill in launcher_text, f"Luna launcher exposes {skill}", failures)
    check("luna-packet-guard" in launcher_text, "Luna launcher invokes packet guard", failures)
    check("--prompt-file was removed" in launcher_text, "legacy Luna packet route fails closed", failures)
    routing_text = (REPO_ROOT / "config" / "AGENTS.md").read_text()
    check("A soft work budget" in routing_text, "resident routing defines soft work budget", failures)
    check(
        "## Proportionality and operating context" in routing_text
        and "including one generated by Codex" in routing_text
        and "lightweight independent premise" in routing_text
        and "even when presented as a local cleanup" in routing_text
        and "the proposal's framing" in routing_text
        and "including your" in routing_text
        and "smallest change that satisfies the active context" in routing_text
        and "advisory or deferred" in routing_text
        and "Automation-safety failures" in routing_text,
        "resident guidance defines proportional operating context",
        failures,
    )
    problem_framing_text = (
        REPO_ROOT
        / "plugins"
        / PLUGIN_NAME
        / "skills"
        / "problem-framing"
        / "SKILL.md"
    ).read_text()
    check(
        "Resolve the active operating context" in problem_framing_text
        and "smallest sufficient scope" in problem_framing_text
        and "deferred concerns" in problem_framing_text,
        "problem framing applies proportional operating context",
        failures,
    )
    review_triage_text = (
        REPO_ROOT
        / "plugins"
        / PLUGIN_NAME
        / "skills"
        / "review-feedback-triage"
        / "SKILL.md"
    ).read_text()
    check(
        "different operating context" in review_triage_text
        and "blocking or advisory status" in review_triage_text
        and "automation-safety failures" in review_triage_text,
        "review triage calibrates findings to operating context",
        failures,
    )
    worker_text = (REPO_ROOT / "agents" / "luna_worker.toml").read_text()
    check("soft work budget" in worker_text, "native Luna agent enforces soft work budget", failures)
    reviewer_text = (REPO_ROOT / "agents" / "terra_reviewer.toml").read_text()
    check(
        all(
            marker in reviewer_text
            for marker in (
                'model = "gpt-5.6-terra"',
                'model_reasoning_effort = "high"',
                'sandbox_mode = "read-only"',
                "This role is advisory",
                "Do not modify files",
            )
        ),
        "Terra reviewer is a read-only high-effort advisor",
        failures,
    )
    check(
        "### Optional Terra review experiment" in routing_text
        and "does not replace the Codex review gate" in routing_text
        and "Do not make Terra review mandatory" in routing_text,
        "resident routing keeps Terra review optional and Codex-owned",
        failures,
    )

    validator = Path.home() / ".codex" / "skills" / ".system" / "plugin-creator" / "scripts" / "validate_plugin.py"
    if validator.is_file():
        result = subprocess.run(
            ["python3", str(validator), str(REPO_ROOT / "plugins" / PLUGIN_NAME)],
            check=False,
        )
        check(result.returncode == 0, "official plugin validator passes", failures)
    else:
        print("SKIP official plugin validator is unavailable")

    if args.installed:
        home = args.home.resolve()
        codex_home = (args.codex_home or home / ".codex").resolve()
        ordinary_matches: list[bool] = []
        for target in managed_targets(home, codex_home):
            if target.label == "resident engineering plugin":
                verify_installed_plugin(
                    home,
                    codex_home,
                    target.source,
                    target.destination,
                    failures,
                )
            else:
                target_matches = paths_equal(target.source, target.destination)
                ordinary_matches.append(target_matches)
                check(
                    target_matches,
                    f"installed {target.label} matches",
                    failures,
                )
        check(
            bool(ordinary_matches) and all(ordinary_matches),
            "installed ordinary managed target matches",
            failures,
        )
        try:
            marketplace, _ = load_marketplace(home / ".agents" / "plugins" / "marketplace.json")
            check(marketplace_status(marketplace) == "same", "installed marketplace entry matches", failures)
        except RuntimeError:
            check(False, "installed marketplace entry matches", failures)

    if failures:
        print(f"verification failed: {len(failures)} check(s)", file=sys.stderr)
        return 1
    print("verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
