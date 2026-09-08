from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO_ROOT / "bootstrap"


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake_codex = self.bin / "codex"
        fake_codex.write_text(
            textwrap.dedent(
                """\
                #!/bin/sh
                set -eu
                printf '%s\\n' "$*" >> "$HOME/codex-commands.log"
                if [ "${1:-} ${2:-} ${3:-} ${4:-} ${5:-}" = "plugin list --marketplace personal --json" ]; then
                  if [ "${FAKE_CODEX_FAIL_LIST:-0}" = 1 ]; then
                    exit 8
                  fi
                  if [ -n "${FAKE_CODEX_LIST_FILE:-}" ] && [ -f "$FAKE_CODEX_LIST_FILE" ]; then
                    cat "$FAKE_CODEX_LIST_FILE"
                  else
                    printf '%s\\n' '{"installed": [], "available": []}'
                  fi
                  exit 0
                fi
                if [ "${FAKE_CODEX_FAIL_ADD:-0}" = 1 ] && [ "$1 $2" = "plugin add" ]; then
                  exit 9
                fi
                exit 0
                """
            )
        )
        fake_codex.chmod(0o755)
        self.local = self.root / "local.toml"
        self.local.write_text(
            textwrap.dedent(
                """\
                network_access = true
                trusted_projects = ["~/work"]
                writable_roots = ["~/work", "~/scratch"]
                """
            )
        )
        self.environment = os.environ.copy()
        self.environment["HOME"] = str(self.home)
        self.environment.pop("CODEX_HOME", None)
        self.environment["PATH"] = f"{self.bin}:{self.environment['PATH']}"

    def prepare_installed_plugin_fixture(self, *, version: str | None = None) -> None:
        deployed = self.home / "plugins/resident-engineering-patterns"
        manifest = json.loads(
            (deployed / ".codex-plugin/plugin.json").read_text()
        )
        if version is not None:
            manifest["version"] = version
            (deployed / ".codex-plugin/plugin.json").write_text(
                json.dumps(manifest) + "\n"
            )
        version = manifest["version"]
        cache = (
            self.home
            / ".codex/plugins/cache/personal/resident-engineering-patterns"
            / version
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        if not cache.exists():
            shutil.copytree(deployed, cache)
        list_file = self.root / "plugin-list.json"
        list_file.write_text(
            json.dumps(
                {
                    "installed": [
                        {
                            "pluginId": "resident-engineering-patterns@personal",
                            "name": "resident-engineering-patterns",
                            "marketplaceName": "personal",
                            "version": version,
                            "installed": True,
                            "enabled": True,
                            "source": {"source": "local", "path": str(deployed)},
                            "installPolicy": "AVAILABLE",
                            "authPolicy": "ON_USE",
                        }
                    ],
                    "available": [],
                }
            )
        )
        self.environment["FAKE_CODEX_LIST_FILE"] = str(list_file)
        self.plugin_list_file = list_file

    def install_for_verification(self, *, version: str | None = None) -> None:
        self.run_script("install.py", *self.install_arguments(), "--apply")
        self.prepare_installed_plugin_fixture(version=version)

    def reset_installed_plugin_fixture(self, *, version: str | None = None) -> None:
        deployed = self.home / "plugins/resident-engineering-patterns"
        cache_root = (
            self.home
            / ".codex/plugins/cache/personal/resident-engineering-patterns"
        )
        shutil.rmtree(deployed)
        shutil.copytree(REPO_ROOT / "plugins/resident-engineering-patterns", deployed)
        shutil.rmtree(cache_root, ignore_errors=True)
        self.prepare_installed_plugin_fixture(version=version)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_script(self, script: str, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(BOOTSTRAP / script), *arguments]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
        )
        if result.returncode != expected:
            self.fail(
                f"{command} returned {result.returncode}, expected {expected}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def install_arguments(self) -> list[str]:
        return [
            "--home",
            str(self.home),
            "--local-config",
            str(self.local),
        ]

    def test_render_config_expands_home_and_parses(self) -> None:
        result = self.run_script(
            "render_config.py",
            "--home",
            str(self.home),
            "--local",
            str(self.local),
        )
        self.assertIn(f'[projects."{self.home / "work"}"]', result.stdout)
        self.assertIn(f'  "{self.home / "work"}",', result.stdout)
        self.assertIn(
            f'  "{self.home / "scratch"}",', result.stdout
        )
        self.assertIn("network_access = true", result.stdout)

    def test_example_config_grants_only_the_public_repository_root(self) -> None:
        example = REPO_ROOT / "config/local.example.toml"
        result = self.run_script(
            "render_config.py",
            "--home",
            str(self.home),
            "--local",
            str(example),
        )
        self.assertIn(f'  "{self.home / "codex-exosphere"}",', result.stdout)

    def test_terra_reviewer_is_managed_as_optional_read_only_advisor(self) -> None:
        source = REPO_ROOT / "agents/terra_reviewer.toml"
        self.assertTrue(source.is_file())
        text = source.read_text()
        for marker in (
            'name = "terra_reviewer"',
            'model = "gpt-5.6-terra"',
            'model_reasoning_effort = "high"',
            'sandbox_mode = "read-only"',
            "advisory",
            "Do not modify files",
        ):
            self.assertIn(marker, text)

        routing = (REPO_ROOT / "config/AGENTS.md").read_text()
        for marker in (
            "### Optional Terra review experiment",
            "does not replace the Codex review gate",
            "Do not make Terra review mandatory",
        ):
            self.assertIn(marker, routing)

        self.run_script("install.py", *self.install_arguments(), "--apply")
        target = self.home / ".codex/agents/terra_reviewer.toml"
        self.assertEqual(source.read_bytes(), target.read_bytes())
        self.run_script("uninstall.py", "--home", str(self.home), "--apply")
        self.assertFalse(target.exists())

    def test_plan_apply_verify_and_uninstall(self) -> None:
        plan = self.run_script("install.py", *self.install_arguments())
        self.assertIn("plan only", plan.stdout)
        self.assertFalse((self.home / ".codex").exists())

        self.run_script("install.py", *self.install_arguments(), "--apply")
        state = self.home / ".local/state/codex-exosphere/install-state.json"
        self.assertTrue(state.is_file())
        commands = (self.home / "codex-commands.log").read_text()
        self.assertIn("plugin add resident-engineering-patterns@personal", commands)

        marketplace = json.loads(
            (self.home / ".agents/plugins/marketplace.json").read_text()
        )
        self.assertEqual(
            [item["name"] for item in marketplace["plugins"]],
            ["resident-engineering-patterns"],
        )
        self.prepare_installed_plugin_fixture()
        verification = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
        )
        for diagnostic in (
            "installed ordinary managed target matches",
            "installed plugin canonical semantics match",
            "installed plugin deployment version is valid",
            "installed plugin effective selection is unique",
            "installed plugin selected cache matches deployment",
        ):
            self.assertIn(f"OK   {diagnostic}", verification.stdout)
        self.assertIn("OK   installed Luna launcher matches", verification.stdout)
        observe = self.home / ".codex/bin/codex-observe"
        self.assertEqual(0o755, observe.stat().st_mode & 0o777)
        self.assertEqual(
            0o644,
            (self.home / ".codex/lib/codex_observability/model.py").stat().st_mode & 0o777,
        )
        subprocess.run(
            [str(observe), "--help"],
            check=True,
            env=self.environment,
            text=True,
            capture_output=True,
        )
        path_environment = self.environment.copy()
        path_environment["PATH"] = (
            f'{self.home / ".local/bin"}:{path_environment["PATH"]}'
        )
        resolved = subprocess.run(
            ["codex-observe", "--help"],
            check=True,
            env=path_environment,
            text=True,
            capture_output=True,
        )
        self.assertIn("Content-free local Codex observability", resolved.stdout)
        self.assertTrue(
            (self.home / ".codex/lib/codex_observability/__pycache__").is_dir()
        )
        self.prepare_installed_plugin_fixture()
        self.run_script("verify.py", "--installed", "--home", str(self.home))

        uninstall_plan = self.run_script("uninstall.py", "--home", str(self.home))
        self.assertIn("plan only", uninstall_plan.stdout)
        self.run_script("uninstall.py", "--home", str(self.home), "--apply")
        self.assertFalse(state.exists())
        commands = (self.home / "codex-commands.log").read_text()
        self.assertIn("plugin remove resident-engineering-patterns@personal", commands)
        self.assertFalse((self.home / "plugins/resident-engineering-patterns").exists())
        self.assertFalse((self.home / ".agents/plugins/marketplace.json").exists())

    def test_uninstall_refuses_changed_managed_file(self) -> None:
        self.run_script("install.py", *self.install_arguments(), "--apply")
        launcher = self.home / ".codex/bin/run-luna-worker"
        launcher.write_text(launcher.read_text() + "\n# local change\n")
        result = self.run_script(
            "uninstall.py",
            "--home",
            str(self.home),
            "--apply",
            expected=1,
        )
        self.assertIn("changed or missing managed path", result.stderr)
        self.assertTrue(launcher.exists())

    def test_installed_plugin_accepts_only_version_cachebuster_drift(self) -> None:
        self.install_for_verification(version="0.2.0+codex.release-a1")
        result = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
        )
        self.assertIn(
            "OK   installed plugin canonical semantics match", result.stdout
        )
        self.assertIn(
            "OK   installed plugin deployment version is valid", result.stdout
        )
        self.assertIn(
            "OK   installed plugin selected cache matches deployment",
            result.stdout,
        )

    def test_installed_plugin_rejects_non_version_drift(self) -> None:
        self.install_for_verification()
        deployed = self.home / "plugins/resident-engineering-patterns"
        mutations = {
            "manifest field": lambda: self._change_deployed_manifest_description(),
            "file bytes": lambda: self._deployed_skill().write_text(
                self._deployed_skill().read_text() + "\nlocal drift\n"
            ),
            "path added": lambda: (deployed / "unexpected.txt").write_text("drift\n"),
            "path deleted": lambda: (deployed / "THIRD_PARTY_NOTICES.md").unlink(),
            "duplicate manifest key": self._add_duplicate_manifest_key,
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                self.reset_installed_plugin_fixture()
                mutate()
                result = self.run_script(
                    "verify.py",
                    "--installed",
                    "--home",
                    str(self.home),
                    expected=1,
                )
                self.assertIn(
                    "FAIL installed plugin canonical semantics match",
                    result.stdout,
                )

    def test_installed_plugin_rejects_base_or_cachebuster_version_drift(self) -> None:
        self.install_for_verification()
        for version in (
            "9.9.9+codex.release-a1",
            "0.2.0+codex.UPPER",
            "0.2.0+codex.double--hyphen",
            "0.2.0+codex.trailing-",
            "0.2.0",
        ):
            with self.subTest(version=version):
                self.reset_installed_plugin_fixture(version=version)
                result = self.run_script(
                    "verify.py",
                    "--installed",
                    "--home",
                    str(self.home),
                    expected=1,
                )
                self.assertIn(
                    "FAIL installed plugin deployment version is valid",
                    result.stdout,
                )

    def test_installed_plugin_rejects_selected_cache_tree_drift(self) -> None:
        self.install_for_verification()
        cache = self._selected_cache()
        mutations = {
            "file bytes": lambda: self._cache_skill().write_text(
                self._cache_skill().read_text() + "\ncache drift\n"
            ),
            "path added": lambda: (cache / "unexpected.txt").write_text("drift\n"),
            "file type": self._replace_cache_skill_with_directory,
            "executable bit": lambda: self._cache_skill().chmod(0o755),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                self.reset_installed_plugin_fixture()
                cache = self._selected_cache()
                mutate()
                result = self.run_script(
                    "verify.py",
                    "--installed",
                    "--home",
                    str(self.home),
                    expected=1,
                )
                self.assertIn(
                    "FAIL installed plugin selected cache matches deployment",
                    result.stdout,
                )

    def test_installed_plugin_fails_closed_on_stale_duplicate_or_malformed_selection(self) -> None:
        self.install_for_verification()
        self.environment["FAKE_CODEX_FAIL_LIST"] = "1"
        nonzero = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
            expected=1,
        )
        self.assertIn(
            "FAIL installed plugin effective selection is unique", nonzero.stdout
        )
        self.environment.pop("FAKE_CODEX_FAIL_LIST")
        selection = json.loads(self.plugin_list_file.read_text())
        selection["installed"][0]["version"] = "0.1.0+codex.20260726000000"
        self.plugin_list_file.write_text(json.dumps(selection))
        stale = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
            expected=1,
        )
        self.assertIn(
            "FAIL installed plugin effective selection is unique", stale.stdout
        )

        selection["installed"].append(dict(selection["installed"][0]))
        self.plugin_list_file.write_text(json.dumps(selection))
        duplicate = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
            expected=1,
        )
        self.assertIn(
            "FAIL installed plugin effective selection is unique", duplicate.stdout
        )

        self.plugin_list_file.write_text("not json\n")
        malformed = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
            expected=1,
        )
        self.assertIn(
            "FAIL installed plugin effective selection is unique", malformed.stdout
        )

        self.plugin_list_file.write_text(
            '{"installed": [], "available": [], "unexpected": true}\n'
        )
        invalid_schema = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
            expected=1,
        )
        self.assertIn(
            "FAIL installed plugin effective selection is unique",
            invalid_schema.stdout,
        )

        self.plugin_list_file.write_text(
            '{"installed": [], "installed": [], "available": []}\n'
        )
        duplicate_key = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
            expected=1,
        )
        self.assertIn(
            "FAIL installed plugin effective selection is unique",
            duplicate_key.stdout,
        )

    def test_installed_verification_keeps_exact_non_plugin_diagnostics(self) -> None:
        self.install_for_verification()
        launcher = self.home / ".codex/bin/run-luna-worker"
        launcher.write_text(launcher.read_text() + "\nlocal drift\n")
        result = self.run_script(
            "verify.py",
            "--installed",
            "--home",
            str(self.home),
            expected=1,
        )
        self.assertIn("FAIL installed Luna launcher matches", result.stdout)
        self.assertIn(
            "FAIL installed ordinary managed target matches", result.stdout
        )

    def _deployed_skill(self) -> Path:
        return (
            self.home
            / "plugins/resident-engineering-patterns/skills/bounded-tdd/SKILL.md"
        )

    def _selected_cache(self) -> Path:
        selection = json.loads(self.plugin_list_file.read_text())
        version = selection["installed"][0]["version"]
        return (
            self.home
            / ".codex/plugins/cache/personal/resident-engineering-patterns"
            / version
        )

    def _cache_skill(self) -> Path:
        return self._selected_cache() / "skills/bounded-tdd/SKILL.md"

    def _change_deployed_manifest_description(self) -> None:
        manifest_path = (
            self.home
            / "plugins/resident-engineering-patterns/.codex-plugin/plugin.json"
        )
        manifest = json.loads(manifest_path.read_text())
        manifest["description"] = "semantic drift"
        manifest_path.write_text(json.dumps(manifest) + "\n")

    def _add_duplicate_manifest_key(self) -> None:
        manifest_path = (
            self.home
            / "plugins/resident-engineering-patterns/.codex-plugin/plugin.json"
        )
        manifest_text = manifest_path.read_text().rstrip()
        manifest_path.write_text(
            manifest_text[:-1] + ', \"description\": \"duplicate\"}\\n'
        )

    def _replace_cache_skill_with_directory(self) -> None:
        skill = self._cache_skill()
        skill.unlink()
        skill.mkdir()

    def test_install_refuses_conflicting_destination(self) -> None:
        target = self.home / ".codex/AGENTS.md"
        target.parent.mkdir(parents=True)
        target.write_text("different\n")
        result = self.run_script("install.py", *self.install_arguments(), expected=1)
        self.assertIn("CONFLICT", result.stdout)
        self.assertIn("destination conflicts", result.stderr)
        self.assertEqual(target.read_text(), "different\n")

    def test_failed_plugin_add_rolls_back_created_files(self) -> None:
        self.environment["FAKE_CODEX_FAIL_ADD"] = "1"
        self.run_script(
            "install.py",
            *self.install_arguments(),
            "--apply",
            expected=1,
        )
        self.assertFalse((self.home / "plugins/resident-engineering-patterns").exists())
        self.assertFalse((self.home / ".agents/plugins/marketplace.json").exists())
        self.assertFalse(
            (self.home / ".local/state/codex-exosphere/install-state.json").exists()
        )

    def test_uninstall_preserves_preexisting_identical_file(self) -> None:
        source = REPO_ROOT / "config/AGENTS.md"
        target = self.home / ".codex/AGENTS.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(source.read_bytes())
        target.chmod(source.stat().st_mode)
        self.run_script("install.py", *self.install_arguments(), "--apply")
        self.run_script("uninstall.py", "--home", str(self.home), "--apply")
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_uninstall_refuses_unexpected_state_path(self) -> None:
        self.run_script("install.py", *self.install_arguments(), "--apply")
        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("do not remove\n")
        state_path = self.home / ".local/state/codex-exosphere/install-state.json"
        state = json.loads(state_path.read_text())
        state["created"].append(
            {
                "path": str(unrelated),
                "digest": "attacker-controlled-digest",
            }
        )
        state_path.write_text(json.dumps(state))
        result = self.run_script(
            "uninstall.py",
            "--home",
            str(self.home),
            "--apply",
            expected=1,
        )
        self.assertIn("unexpected path in install state", result.stderr)
        self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
