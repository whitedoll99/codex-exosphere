from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from evals import harness


class EvalHarnessTests(unittest.TestCase):
    def test_all_cases_and_schemas_validate(self) -> None:
        cases = harness.load_cases()

        self.assertEqual(
            {case["id"] for case in cases},
            {
                "routing-local-bug",
                "routing-large-defined-subsystem",
                "routing-ambiguous-feature",
                "routing-unknown-failure",
                "routing-public-contract",
                "routing-review-feedback",
                "routing-architecture-tradeoff",
                "luna-discovered-public-boundary",
                "sol-review-seeded-defects",
            },
        )
        self.assertEqual([], harness.validate_cases())

        review_schema = json.loads(
            (harness.SCHEMAS_DIR / "review-output.schema.json").read_text()
        )
        self.assertFalse(
            review_schema["properties"]["findings"]["items"]["additionalProperties"]
        )
        for schema_name in (
            "routing-output.schema.json",
            "review-output.schema.json",
            "boundary-output.schema.json",
        ):
            schema = json.loads((harness.SCHEMAS_DIR / schema_name).read_text())
            self.assertEqual(set(schema["properties"]), set(schema["required"]))

    def test_offline_commands_do_not_invoke_process_runner(self) -> None:
        with mock.patch.object(
            harness.subprocess,
            "run",
            side_effect=AssertionError("offline command invoked subprocess"),
        ):
            for arguments in (["list"], ["validate"], ["plan"], ["plan", "--case", "routing-local-bug"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, harness.main(arguments))
                self.assertTrue(output.getvalue())

    def test_case_filter_and_unknown_case_error(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, harness.main(["plan", "--case", "routing-local-bug"]))
        self.assertIn("routing-local-bug", output.getvalue())
        self.assertNotIn("routing-unknown-failure", output.getvalue())

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(2, harness.main(["plan", "--case", "does-not-exist"]))
        self.assertIn("Unknown case", errors.getvalue())

    def test_jsonl_parser_ignores_unknown_events_and_extracts_final_result(self) -> None:
        text = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "t"}),
                json.dumps({"type": "future.event", "payload": {"x": 1}}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": json.dumps(
                                {"route": "luna", "selected_skills": ["bounded-tdd"]}
                            ),
                        },
                    }
                ),
            ]
        )

        parsed = harness.parse_jsonl(text)
        self.assertEqual(3, len(parsed.events))
        self.assertEqual(["future.event"], parsed.unknown_event_types)
        self.assertEqual(
            {"route": "luna", "selected_skills": ["bounded-tdd"]},
            harness.extract_final_result(parsed.events),
        )

    def test_skill_path_evidence_is_observed_from_event_content(self) -> None:
        events = [
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": (
                        "Read /tmp/plugin/skills/bounded-tdd/SKILL.md and "
                        "plugins/resident/skills/systematic-diagnosis/SKILL.md"
                    ),
                    "aggregated_output": (
                        "plugins/resident/skills/problem-framing/SKILL.md"
                    ),
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": "plugins/resident/skills/contract-design/SKILL.md",
                },
            },
        ]

        self.assertEqual(
            ["bounded-tdd", "systematic-diagnosis"],
            harness.extract_skill_reads(events),
        )

    def test_routing_scoring_checks_required_and_forbidden_skills(self) -> None:
        case = harness.case_by_id("routing-local-bug")

        passing = harness.score_routing(case, "luna", ["bounded-tdd"])
        self.assertTrue(passing.passed)

        failing = harness.score_routing(
            case,
            "sol",
            ["bounded-tdd", "systematic-diagnosis"],
        )
        self.assertFalse(failing.passed)
        self.assertIn("route", {check["id"] for check in failing.checks if not check["passed"]})
        self.assertIn(
            "forbidden-skills",
            {check["id"] for check in failing.checks if not check["passed"]},
        )

    def test_output_conflict_refuses_non_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "case-output"
            output.mkdir()
            (output / "report.json").write_text("existing\n")

            with self.assertRaises(harness.EvaluationError):
                harness.prepare_output_dir(output, explicit=True)

    def test_artifact_redaction_removes_auth_paths_and_token_like_values(self) -> None:
        redacted = harness._redact_text(
            "failed at /home/example/.codex/auth.json "
            "OPENAI_API_KEY=sk-1234567890abcdef Bearer abc.def"
        )

        self.assertNotIn("auth.json", redacted)
        self.assertNotIn("sk-1234567890abcdef", redacted)
        self.assertNotIn("Bearer abc.def", redacted)

    def test_temporary_codex_environment_uses_symlinks_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as source:
            source_home = Path(source)
            (source_home / "auth.json").write_text("credentials\n")
            (source_home / "config.toml").write_text("model = 'test'\n")
            with mock.patch.dict("os.environ", {"CODEX_HOME": source}, clear=False):
                with harness._temporary_codex_environment() as environment:
                    temporary_home = Path(environment["CODEX_HOME"])
                    self.assertNotEqual(source_home, temporary_home)
                    self.assertTrue((temporary_home / "auth.json").is_symlink())
                    self.assertEqual(source_home / "auth.json", (temporary_home / "auth.json").resolve())
            self.assertFalse(temporary_home.exists())

    def test_luna_boundary_scoring_requires_clean_worktree_and_decision_packet(self) -> None:
        case = harness.case_by_id("luna-discovered-public-boundary")
        packet = {
            "packet_type": "decision",
            "changes_made": False,
            "boundary": {
                "unresolved": "The public default has two incompatible meanings.",
                "owner": "sol",
                "options": ["preserve old meaning", "adopt new meaning"],
            },
        }
        passing = harness.score_luna_boundary(
            case, packet, "", "", "before", "before", ["bounded-tdd"]
        )
        self.assertTrue(passing.passed)

        failing = harness.score_luna_boundary(
            case,
            packet,
            " M src/cli.py\n",
            "diff",
            "before",
            "after",
            ["bounded-tdd"],
        )
        self.assertFalse(failing.passed)
        self.assertIn(
            "clean-worktree",
            {check["id"] for check in failing.checks if not check["passed"]},
        )

    def test_luna_boundary_fixture_contains_a_real_contract_conflict(self) -> None:
        fixture = harness.FIXTURES_DIR / "luna-discovered-public-boundary"
        namespace: dict[str, object] = {}
        exec((fixture / "src/cli.py").read_text(), namespace)

        self.assertEqual(0, namespace["parse_limit"](""))
        self.assertIn(
            'parse_limit("") == DEFAULT_LIMIT',
            (fixture / "tests/test_cli.py").read_text(),
        )
        self.assertIn(
            "return parse_limit(raw)",
            (fixture / "src/legacy_adapter.py").read_text(),
        )

    def test_luna_runner_captures_fake_launcher_evidence_without_model_call(self) -> None:
        commands: list[list[str]] = []

        def fake_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            if command[0] == "/tmp/fake-luna":
                packet = Path(command[command.index("--output") + 1])
                metrics = Path(command[command.index("--metrics") + 1])
                packet.write_text(
                    json.dumps(
                        {
                            "packet_type": "decision",
                            "changes_made": False,
                            "boundary": {
                                "unresolved": "Two public meanings remain possible.",
                                "owner": "sol",
                                "options": ["keep legacy", "adopt new"],
                            },
                        }
                    )
                )
                metrics.write_text(
                    json.dumps({"observed_skills": ["bounded-tdd"]})
                )
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "launcher\n",
                    "luna-worker: completed\n",
                )
            return subprocess.run(command, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "luna"
            output.mkdir()
            report = harness.run_luna_boundary_case(
                harness.case_by_id("luna-discovered-public-boundary"),
                output,
                command_runner=fake_runner,
                launcher=Path("/tmp/fake-luna"),
            )
            self.assertEqual("passed", report["status"])
            self.assertTrue((output / "git-status.txt").exists())
            self.assertTrue((output / "delegation-packet.json").exists())
            self.assertEqual(["bounded-tdd"], report["observed_skills"])
        self.assertTrue(any(command[0] == "/tmp/fake-luna" for command in commands))
        luna_command = next(command for command in commands if command[0] == "/tmp/fake-luna")
        self.assertIn("--packet-file", luna_command)
        self.assertNotIn("--prompt-file", luna_command)


    def test_sol_review_scoring_requires_seeded_findings_and_read_only_snapshot(self) -> None:
        case = harness.case_by_id("sol-review-seeded-defects")
        result = {
            "route": "sol",
            "read_only_confirmed": True,
            "findings": [
                {"id": "scope-creep", "summary": "An unapproved file changed."},
                {"id": "empty-input-regression", "summary": "Empty input now raises."},
                {"id": "coverage-gap", "summary": "Tests omit the empty-input case."},
            ],
        }
        before = {"files": {"src/a.py": "digest"}, "status": " M src/a.py"}
        passing = harness.score_sol_review(case, result, before, before)
        self.assertTrue(passing.passed)

        failing = harness.score_sol_review(
            case,
            {"findings": [{"id": "scope-creep"}]},
            before,
            {"files": {"src/a.py": "different"}, "status": " M src/a.py"},
        )
        self.assertFalse(failing.passed)
        self.assertIn(
            "read-only",
            {check["id"] for check in failing.checks if not check["passed"]},
        )

        semantically_equivalent = {
            "route": "sol",
            "read_only_confirmed": True,
            "findings": [
                {
                    "id": "empty-input-regression",
                    "summary": "Empty lists raise unexpectedly.",
                },
                {
                    "id": "missing-empty-input-coverage",
                    "summary": "The only test is non-empty; no test protects empty input.",
                },
                {
                    "id": "unrelated-untracked-doc",
                    "summary": "A file outside the requested implementation is present.",
                },
            ],
        }
        self.assertTrue(
            harness.score_sol_review(case, semantically_equivalent, before, before).passed
        )

    def test_sol_runner_scores_fake_structured_review_and_preserves_candidate(self) -> None:
        commands: list[list[str]] = []

        def fake_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            if command and command[0] == "codex":
                result = {
                    "route": "sol",
                    "findings": [
                        {"id": "scope-creep", "summary": "unapproved file"},
                        {"id": "empty-input-regression", "summary": "empty input raises"},
                        {"id": "coverage-gap", "summary": "no empty test"},
                    ],
                    "read_only_confirmed": True,
                }
                event = {"type": "item.completed", "item": {"text": json.dumps(result)}}
                return subprocess.CompletedProcess(command, 0, json.dumps(event) + "\n", "")
            return subprocess.run(command, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "sol"
            output.mkdir()
            report = harness.run_sol_review_case(
                harness.case_by_id("sol-review-seeded-defects"),
                output,
                command_runner=fake_runner,
            )

            self.assertEqual("passed", report["status"])
            self.assertTrue((output / "candidate.diff").exists())

        codex_command = next(command for command in commands if command[0] == "codex")
        self.assertIn("--ephemeral", codex_command)
        self.assertIn("--json", codex_command)
        self.assertIn("--sandbox", codex_command)
        self.assertIn("read-only", codex_command)
        self.assertIn("--output-schema", codex_command)

    def test_fixture_materialization_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            destination = Path(temporary) / "destination"
            outside = Path(temporary) / "outside.txt"
            source.mkdir()
            destination.mkdir()
            outside.write_text("secret\n")
            (source / "escape").symlink_to(outside)

            with self.assertRaises(harness.EvaluationError):
                harness.materialize_fixture(source, destination)

    def test_fixture_materialization_rejects_symlink_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            outside = root / "outside"
            source.mkdir()
            outside.mkdir()
            (source / "input.txt").write_text("input\n")
            destination = root / "destination"
            destination.symlink_to(outside, target_is_directory=True)

            with self.assertRaises(harness.EvaluationError):
                harness.materialize_fixture(source, destination)


if __name__ == "__main__":
    unittest.main()
