from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "bin/luna-packet-guard"


def packet(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "version": 1,
        "mode": "implementation",
        "objective": "Implement one bounded fixture behavior.",
        "acceptance_criteria": ["The focused fixture test passes."],
        "allowed_changes": ["src/allowed.txt", "tests/**"],
        "read_only_context": ["README.md"],
        "non_goals": ["Do not change the public contract."],
        "verification": ["test -f src/allowed.txt"],
        "authorization": {"commit": False, "push": False},
        "existing_changes": [],
        "soft_budget": {
            "review_unit": "One fixture behavior and its focused test.",
            "stop_conditions": ["Another component must change."],
        },
    }
    value.update(overrides)
    return value


class LunaPacketGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.test")
        self.git("config", "user.name", "Fixture")
        (self.repo / "README.md").write_text("fixture\n")
        (self.repo / "src").mkdir()
        (self.repo / "src/allowed.txt").write_text("before\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.packet_path = self.root / "packet.json"
        self.rendered = self.root / "rendered.md"
        self.normalized = self.root / "normalized.json"
        self.before = self.root / "before.json"
        self.report = self.root / "report.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *arguments],
            check=True,
            text=True,
            capture_output=True,
        )

    def write_packet(self, value: dict[str, object] | None = None) -> None:
        self.packet_path.write_text(json.dumps(value or packet()))

    def guard(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(GUARD), *arguments],
            text=True,
            capture_output=True,
        )
        if result.returncode != expected:
            self.fail(
                f"guard returned {result.returncode}, expected {expected}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def snapshot(self) -> None:
        self.guard(
            "snapshot", "--packet", str(self.packet_path),
            "--workspace", str(self.repo), "--output", str(self.before),
        )

    def check(self, expected: int = 0) -> dict[str, object]:
        self.guard(
            "check", "--packet", str(self.packet_path),
            "--workspace", str(self.repo), "--before", str(self.before),
            "--output", str(self.report), expected=expected,
        )
        return json.loads(self.report.read_text())

    def test_valid_packet_renders_complete_contract(self) -> None:
        self.write_packet()
        result = self.guard(
            "validate", "--packet", str(self.packet_path),
            "--render", str(self.rendered), "--normalized", str(self.normalized),
        )
        rendered = self.rendered.read_text()
        self.assertEqual("implementation\n", result.stdout)
        self.assertIn("# Luna delegation packet v1", rendered)
        self.assertIn("## Soft work budget", rendered)
        self.assertIn("Commit authorized: false", rendered)
        self.assertEqual(packet(), json.loads(self.normalized.read_text()))

    def test_missing_budget_unknown_field_and_commit_are_rejected(self) -> None:
        cases = []
        missing = packet()
        del missing["soft_budget"]
        cases.append(missing)
        cases.append(packet(extra="unexpected"))
        cases.append(packet(authorization={"commit": True, "push": False}))
        for value in cases:
            with self.subTest(value=value):
                self.write_packet(value)
                self.guard(
                    "validate", "--packet", str(self.packet_path),
                    "--render", str(self.rendered), "--normalized", str(self.normalized),
                    expected=2,
                )

    def test_unsafe_paths_read_only_writes_oversize_and_symlink_are_rejected(self) -> None:
        invalid_packets = [
            packet(allowed_changes=["../outside"]),
            packet(allowed_changes=[".git/config"]),
            packet(allowed_changes=["src/*.py"]),
            packet(mode="read-only", allowed_changes=["src/allowed.txt"]),
        ]
        for value in invalid_packets:
            with self.subTest(value=value):
                self.write_packet(value)
                self.guard(
                    "validate", "--packet", str(self.packet_path),
                    "--render", str(self.rendered), "--normalized", str(self.normalized),
                    expected=2,
                )
        self.packet_path.write_text(" " * (64 * 1024 + 1))
        self.guard(
            "validate", "--packet", str(self.packet_path),
            "--render", str(self.rendered), "--normalized", str(self.normalized),
            expected=2,
        )
        target = self.root / "real-packet.json"
        target.write_text(json.dumps(packet()))
        self.packet_path.unlink()
        self.packet_path.symlink_to(target)
        self.guard(
            "validate", "--packet", str(self.packet_path),
            "--render", str(self.rendered), "--normalized", str(self.normalized),
            expected=2,
        )

    def test_preflight_requires_exact_dirty_declaration_and_no_overlap(self) -> None:
        (self.repo / "README.md").write_text("user work\n")
        self.write_packet()
        self.guard(
            "snapshot", "--packet", str(self.packet_path),
            "--workspace", str(self.repo), "--output", str(self.before), expected=2,
        )
        self.write_packet(packet(existing_changes=["README.md"]))
        self.snapshot()
        self.write_packet(
            packet(existing_changes=["README.md"], allowed_changes=["README.md"])
        )
        self.guard(
            "snapshot", "--packet", str(self.packet_path),
            "--workspace", str(self.repo), "--output", str(self.before), expected=2,
        )

    def test_allowed_change_and_glob_pass_postflight(self) -> None:
        self.write_packet()
        self.snapshot()
        (self.repo / "src/allowed.txt").write_text("after\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/fixture.txt").write_text("new\n")
        report = self.check()
        self.assertTrue(report["passed"])
        self.assertEqual(["src/allowed.txt", "tests/fixture.txt"], report["touched_paths"])

    def test_unauthorized_file_fails_and_is_not_reverted(self) -> None:
        self.write_packet()
        self.snapshot()
        outside = self.repo / "outside.txt"
        outside.write_text("evidence\n")
        report = self.check(expected=78)
        self.assertEqual(["outside.txt"], report["unauthorized_paths"])
        self.assertEqual("evidence\n", outside.read_text())

    def test_preexisting_dirty_mutation_and_commit_fail(self) -> None:
        (self.repo / "README.md").write_text("user work\n")
        self.write_packet(packet(existing_changes=["README.md"]))
        self.snapshot()
        (self.repo / "README.md").write_text("worker overwrote user work\n")
        report = self.check(expected=78)
        self.assertEqual(["README.md"], report["unauthorized_paths"])

        self.git("restore", "README.md")
        self.write_packet()
        self.snapshot()
        (self.repo / "src/allowed.txt").write_text("committed\n")
        self.git("add", "src/allowed.txt")
        self.git("commit", "-qm", "unauthorized")
        report = self.check(expected=78)
        self.assertTrue(report["head_changed"])

    def test_workspace_must_be_git_root(self) -> None:
        self.write_packet()
        self.guard(
            "snapshot", "--packet", str(self.packet_path),
            "--workspace", str(self.repo / "src"), "--output", str(self.before),
            expected=2,
        )


if __name__ == "__main__":
    unittest.main()
