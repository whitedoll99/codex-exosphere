from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.test_observability_core import event


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "bin/codex-observe"


class ObservabilityCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = self.root / "state/events.sqlite3"
        self.event_file = self.root / "event.json"
        self.event_file.write_text(json.dumps(event()))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [str(CLI), *arguments],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        if result.returncode != expected:
            self.fail(
                f"CLI returned {result.returncode}, expected {expected}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def test_emit_is_idempotent_and_queries_use_json_contract(self) -> None:
        first = self.run_cli("emit", "--file", str(self.event_file), "--db", str(self.db))
        second = self.run_cli("emit", "--file", str(self.event_file), "--db", str(self.db))
        summary = self.run_cli("summary", "--db", str(self.db), "--json")
        tasks = self.run_cli("tasks", "--db", str(self.db), "--json")
        timeline = self.run_cli("task", "task-001", "--db", str(self.db), "--json")

        self.assertEqual("recorded evt-001\n", first.stdout)
        self.assertEqual("duplicate evt-001\n", second.stdout)
        self.assertEqual(1, json.loads(summary.stdout)["totals"]["events"])
        self.assertEqual("task-001", json.loads(tasks.stdout)[0]["task_id"])
        self.assertEqual("evt-001", json.loads(timeline.stdout)[0]["event_id"])

    def test_invalid_or_symlink_event_fails_before_database_creation(self) -> None:
        self.event_file.write_text(json.dumps({"prompt": "secret"}))
        result = self.run_cli(
            "emit", "--file", str(self.event_file), "--db", str(self.db), expected=2
        )
        self.assertIn("invalid event fields", result.stderr)
        self.assertFalse(self.db.exists())

        target = self.root / "target.json"
        target.write_text(json.dumps(event()))
        self.event_file.unlink()
        self.event_file.symlink_to(target)
        result = self.run_cli(
            "emit", "--file", str(self.event_file), "--db", str(self.db), expected=2
        )
        self.assertIn("symlink", result.stderr)
        self.assertFalse(self.db.exists())

    def test_import_luna_maps_only_safe_metrics_subset(self) -> None:
        metrics = self.root / "luna-metrics.json"
        metrics.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "succeeded",
                    "model": "gpt-5.6-luna",
                    "reasoning_effort": "xhigh",
                    "elapsed_seconds": 23,
                    "observed_skills": ["bounded-tdd"],
                    "usage": {
                        "input_tokens": 24559,
                        "cached_input_tokens": 17920,
                        "output_tokens": 822,
                    },
                    "scope": {"passed": True},
                    "prompt": "this unknown source field must not be persisted",
                }
            )
        )
        self.run_cli(
            "import-luna",
            "--metrics", str(metrics),
            "--task-id", "task-live-1",
            "--run-id", "run-live-1",
            "--event-id", "event-live-1",
            "--occurred-at", "2026-07-16T12:30:00Z",
            "--task-kind", "implementation",
            "--db", str(self.db),
        )
        timeline = json.loads(
            self.run_cli("task", "task-live-1", "--db", str(self.db), "--json").stdout
        )
        imported = timeline[0]
        self.assertEqual(23000, imported["duration_ms"])
        self.assertEqual("passed", imported["scope_status"])
        self.assertNotIn("prompt", imported)
        self.assertNotIn("this unknown", self.db.read_bytes().decode("utf-8", errors="ignore"))

    def test_query_limit_is_bounded(self) -> None:
        self.run_cli("emit", "--file", str(self.event_file), "--db", str(self.db))
        result = self.run_cli("tasks", "--db", str(self.db), "--limit", "201", expected=2)
        self.assertIn("limit", result.stderr)

    def test_corrupted_database_fails_without_traceback(self) -> None:
        self.db.parent.mkdir(mode=0o700)
        self.db.write_bytes(b"not a sqlite database")
        self.db.chmod(0o600)
        result = self.run_cli("summary", "--db", str(self.db), expected=2)
        self.assertIn("codex-observe:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
