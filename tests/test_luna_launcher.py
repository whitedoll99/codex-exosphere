from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "bin/run-luna-worker"
PATTERNS = REPO_ROOT / "plugins/resident-engineering-patterns"


class LunaLauncherContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.source_codex_home = self.root / "source-codex-home"
        self.source_codex_home.mkdir()
        (self.source_codex_home / "auth.json").write_text("fixture auth\n")
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        subprocess.run(["git", "-C", str(self.workspace), "init", "-q"], check=True)
        subprocess.run(
            ["git", "-C", str(self.workspace), "config", "user.email", "fixture@example.test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.workspace), "config", "user.name", "Fixture"],
            check=True,
        )
        (self.workspace / "README.md").write_text("fixture\n")
        (self.workspace / "src").mkdir()
        (self.workspace / "src/allowed.txt").write_text("before\n")
        subprocess.run(["git", "-C", str(self.workspace), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.workspace), "commit", "-qm", "fixture"], check=True
        )
        self.packet = self.root / "packet.json"
        self.write_packet()
        self.output = self.root / "result.txt"
        self.metrics = self.root / "metrics.json"
        self.jsonl = self.root / "fake.jsonl"
        self.stderr = self.root / "fake.stderr"
        self.result = self.root / "fake-result.txt"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake_codex = self.bin / "codex"
        fake_codex.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                printf '%s\n' "$*" >> "$FAKE_CODEX_COMMANDS"
                if [[ "${1:-}" == plugin ]]; then
                  if [[ "${FAKE_CODEX_PLUGIN_EXIT:-0}" != 0 ]]; then
                    printf '%s\n' '/tmp/.codex/auth.json Bearer plugin.secret sk-1234567890abcdef' >&2
                    exit "$FAKE_CODEX_PLUGIN_EXIT"
                  fi
                  exit 0
                fi
                if [[ -n "${FAKE_CODEX_WRITE_PATH:-}" ]]; then
                  mkdir -p -- "$(dirname -- "$FAKE_CODEX_WRITE_PATH")"
                  printf '%s\n' 'worker change' > "$FAKE_CODEX_WRITE_PATH"
                fi
                if [[ -n "${FAKE_CODEX_MUTATE_PACKET:-}" ]]; then
                  printf '%s\n' '{}' > "$FAKE_CODEX_MUTATE_PACKET"
                fi
                output=''
                while (( $# > 0 )); do
                  if [[ "$1" == --output-last-message ]]; then
                    output="$2"
                    shift 2
                  else
                    shift
                  fi
                done
                cat >/dev/null
                cat "$FAKE_CODEX_JSONL"
                cat "$FAKE_CODEX_STDERR" >&2
                if [[ -n "$output" && -f "$FAKE_CODEX_RESULT" ]]; then
                  cp "$FAKE_CODEX_RESULT" "$output"
                fi
                exit "${FAKE_CODEX_EXIT:-0}"
                """
            )
        )
        fake_codex.chmod(0o755)
        self.commands = self.root / "commands.log"
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "HOME": str(self.home),
                "CODEX_HOME": str(self.source_codex_home),
                "PATH": f"{self.bin}:{self.environment['PATH']}",
                "RESIDENT_ENGINEERING_PATTERNS_ROOT": str(PATTERNS),
                "FAKE_CODEX_COMMANDS": str(self.commands),
                "FAKE_CODEX_JSONL": str(self.jsonl),
                "FAKE_CODEX_STDERR": str(self.stderr),
                "FAKE_CODEX_RESULT": str(self.result),
            }
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_packet(self, **overrides: object) -> None:
        value: dict[str, object] = {
            "version": 1,
            "mode": "implementation",
            "objective": "Implement the bounded fixture behavior.",
            "acceptance_criteria": ["The focused fixture test passes."],
            "allowed_changes": ["src/allowed.txt"],
            "read_only_context": ["README.md"],
            "non_goals": ["Do not change public contracts."],
            "verification": ["test -f src/allowed.txt"],
            "authorization": {"commit": False, "push": False},
            "existing_changes": [],
            "soft_budget": {
                "review_unit": "One fixture behavior.",
                "stop_conditions": ["Another component must change."],
            },
        }
        value.update(overrides)
        self.packet.write_text(json.dumps(value))

    def run_launcher(self, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                str(LAUNCHER),
                "--cd",
                str(self.workspace),
                "--packet-file",
                str(self.packet),
                "--output",
                str(self.output),
                "--metrics",
                str(self.metrics),
            ],
            cwd=REPO_ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
        )
        if result.returncode != expected:
            self.fail(
                f"launcher returned {result.returncode}, expected {expected}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def test_success_returns_only_final_result_and_safe_metrics(self) -> None:
        self.result.write_text("concise result\n")
        self.stderr.write_text("raw command output and diff must stay private\n")
        self.jsonl.write_text(
            "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": "secret-session"}),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "sed -n 1,200p /tmp/plugin/skills/bounded-tdd/SKILL.md && private command",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "turn.completed",
                            "usage": {
                                "input_tokens": 120,
                                "cached_input_tokens": 40,
                                "output_tokens": 8,
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        result = self.run_launcher()

        self.assertEqual("concise result\n", result.stdout)
        self.assertIn("luna-worker: started", result.stderr)
        self.assertIn("luna-worker: completed", result.stderr)
        self.assertNotIn("private command", result.stderr + result.stdout)
        self.assertNotIn("raw command output", result.stderr + result.stdout)
        metrics = json.loads(self.metrics.read_text())
        self.assertEqual(0o600, self.metrics.stat().st_mode & 0o777)
        self.assertEqual("succeeded", metrics["status"])
        self.assertEqual(120, metrics["usage"]["input_tokens"])
        self.assertEqual(80, metrics["derived_usage"]["uncached_input_tokens"])
        self.assertEqual(88, metrics["derived_usage"]["uncached_input_plus_output_tokens"])
        self.assertEqual(1, metrics["event_counts"]["turn.completed"])
        self.assertEqual(["bounded-tdd"], metrics["observed_skills"])
        self.assertNotIn("secret-session", self.metrics.read_text())
        self.assertIn("--json", self.commands.read_text())
        self.assertIn("--sandbox workspace-write", self.commands.read_text())
        self.assertTrue(metrics["scope"]["passed"])

    def test_failure_preserves_exit_and_redacts_bounded_diagnostic(self) -> None:
        self.environment["FAKE_CODEX_EXIT"] = "7"
        self.stderr.write_text(
            "/home/example/.codex/auth.json Bearer abc.def "
            "OPENAI_API_KEY=sk-1234567890abcdef\n"
        )
        self.jsonl.write_text(
            json.dumps(
                {
                    "type": "error",
                    "message": "request failed with sk-abcdefghijklmnop",
                }
            )
            + "\n"
        )

        result = self.run_launcher(expected=7)

        self.assertEqual("", result.stdout)
        self.assertIn("luna-worker: failed (exit=7", result.stderr)
        for secret in ("auth.json", "Bearer abc.def", "sk-1234567890abcdef", "sk-abcdefghijklmnop"):
            self.assertNotIn(secret, result.stderr)
        self.assertLess(len(result.stderr.encode()), 4096)
        metrics = json.loads(self.metrics.read_text())
        self.assertEqual("failed", metrics["status"])
        self.assertEqual(7, metrics["exit_code"])

    def test_malformed_jsonl_fails_closed(self) -> None:
        self.result.write_text("must not be reported as success\n")
        self.stderr.write_text("")
        self.jsonl.write_text("not-json\n")

        result = self.run_launcher(expected=65)

        self.assertEqual("", result.stdout)
        self.assertIn("malformed line", result.stderr)
        metrics = json.loads(self.metrics.read_text())
        self.assertEqual("failed", metrics["status"])
        self.assertEqual(1, metrics["malformed_jsonl_lines"])

    def test_plugin_setup_failure_is_redacted(self) -> None:
        self.environment["FAKE_CODEX_PLUGIN_EXIT"] = "9"
        self.jsonl.write_text("")
        self.stderr.write_text("")

        result = self.run_launcher(expected=1)

        for secret in ("auth.json", "Bearer plugin.secret", "sk-1234567890abcdef"):
            self.assertNotIn(secret, result.stderr)
        self.assertFalse(self.metrics.exists())

    def test_missing_budget_is_rejected_before_codex_is_called(self) -> None:
        value = json.loads(self.packet.read_text())
        del value["soft_budget"]
        self.packet.write_text(json.dumps(value))

        result = self.run_launcher(expected=2)

        self.assertIn("missing=['soft_budget']", result.stderr)
        self.assertFalse(self.commands.exists())
        self.assertFalse(self.metrics.exists())

    def test_removed_prompt_file_route_is_rejected_before_codex_is_called(self) -> None:
        legacy = self.root / "legacy.md"
        legacy.write_text("legacy packet\n")
        result = subprocess.run(
            [
                str(LAUNCHER), "--cd", str(self.workspace),
                "--prompt-file", str(legacy), "--output", str(self.output),
            ],
            cwd=REPO_ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("was removed", result.stderr)
        self.assertFalse(self.commands.exists())

    def test_scope_violation_fails_without_reverting_evidence(self) -> None:
        self.result.write_text("must not be reported\n")
        self.stderr.write_text("")
        self.jsonl.write_text(json.dumps({"type": "turn.completed", "usage": {}}) + "\n")
        outside = self.workspace / "outside.txt"
        self.environment["FAKE_CODEX_WRITE_PATH"] = str(outside)
        self.environment["FAKE_CODEX_MUTATE_PACKET"] = str(self.packet)

        result = self.run_launcher(expected=78)

        self.assertEqual("", result.stdout)
        self.assertIn("unauthorized_paths=['outside.txt']", result.stderr)
        self.assertEqual("worker change\n", outside.read_text())
        self.assertEqual("{}\n", self.packet.read_text())
        metrics = json.loads(self.metrics.read_text())
        self.assertEqual(78, metrics["exit_code"])
        self.assertFalse(metrics["scope"]["passed"])

    def test_read_only_packet_selects_read_only_sandbox(self) -> None:
        self.write_packet(mode="read-only", allowed_changes=[])
        self.result.write_text("read-only result\n")
        self.stderr.write_text("")
        self.jsonl.write_text(json.dumps({"type": "turn.completed", "usage": {}}) + "\n")

        self.run_launcher()

        self.assertIn("--sandbox read-only", self.commands.read_text())


if __name__ == "__main__":
    unittest.main()
