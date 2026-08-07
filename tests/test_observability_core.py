from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from codex_observability import model
from codex_observability.model import EventValidationError, normalize_event
from codex_observability.store import EventConflictError, EventStore, default_db_path


def event(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "event_id": "evt-001",
        "occurred_at": "2026-07-16T12:00:00Z",
        "task_id": "task-001",
        "run_id": "run-001",
        "event_type": "delegation.completed",
        "actor": "luna",
        "emitter": "luna-launcher",
        "task_kind": "implementation",
        "outcome": "succeeded",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "xhigh",
        "duration_ms": 23000,
        "input_tokens": 24559,
        "cached_input_tokens": 17920,
        "output_tokens": 822,
        "skills": ["verification-before-reporting", "bounded-tdd"],
        "fix_round": 0,
        "finding_count": None,
        "scope_status": "passed",
        "decision_reason": None,
    }
    value.update(overrides)
    return value


class EventModelTests(unittest.TestCase):
    def test_packaged_json_schema_matches_code_contract(self) -> None:
        schema = json.loads(
            (
                Path(model.__file__).with_name("schema") / "event-v1.schema.json"
            ).read_text()
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(model.FIELDS, set(schema["required"]))
        self.assertEqual(model.FIELDS, set(schema["properties"]))
        self.assertEqual(model.EVENT_TYPES, set(schema["properties"]["event_type"]["enum"]))
        self.assertEqual(model.ACTORS, set(schema["properties"]["actor"]["enum"]))
        self.assertEqual(model.TASK_KINDS, set(schema["properties"]["task_kind"]["enum"]))
        self.assertEqual(model.OUTCOMES, set(schema["properties"]["outcome"]["enum"]))
        self.assertEqual(
            model.SCOPE_STATUSES, set(schema["properties"]["scope_status"]["enum"])
        )
    def test_normalizes_valid_event_without_content_fields(self) -> None:
        normalized = normalize_event(event())

        self.assertEqual(
            ["bounded-tdd", "verification-before-reporting"], normalized["skills"]
        )
        self.assertEqual("2026-07-16T12:00:00Z", normalized["occurred_at"])

    def test_rejects_unknown_missing_oversized_and_content_bearing_fields(self) -> None:
        cases = []
        unknown = event(prompt="do not store this")
        cases.append(unknown)
        missing = event()
        del missing["event_id"]
        cases.append(missing)
        cases.append(event(task_id="x" * 129))
        cases.append(event(model="natural language with spaces"))
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(EventValidationError):
                    normalize_event(value)

    def test_rejects_invalid_counts_time_and_lifecycle_combinations(self) -> None:
        cases = [
            event(input_tokens=-1),
            event(input_tokens=1, cached_input_tokens=2),
            event(occurred_at="2026-07-16T12:00:00+09:00"),
            event(event_type="delegation.started", outcome="succeeded"),
            event(event_type="decision.returned", outcome="failed"),
            event(event_type="scope.checked", outcome="succeeded", scope_status="violated"),
            event(skills=["bounded-tdd", "bounded-tdd"]),
        ]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(EventValidationError):
                    normalize_event(value)

    def test_nullable_observations_are_distinct_from_zero(self) -> None:
        value = event(
            model=None,
            reasoning_effort=None,
            duration_ms=None,
            input_tokens=None,
            cached_input_tokens=None,
            output_tokens=None,
            skills=[],
            fix_round=None,
            finding_count=None,
            scope_status="not_checked",
        )
        normalized = normalize_event(value)
        self.assertIsNone(normalized["duration_ms"])
        self.assertEqual([], normalized["skills"])


class EventStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = self.root / "state" / "events.sqlite3"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_records_idempotently_and_conflicts_on_changed_reuse(self) -> None:
        with EventStore(self.db) as store:
            self.assertTrue(store.record(event()))
            self.assertFalse(store.record(event(skills=["bounded-tdd", "verification-before-reporting"])))
            with self.assertRaises(EventConflictError):
                store.record(event(output_tokens=823))
            with self.assertRaises(EventConflictError):
                store.record(event(event_id="evt-002", task_kind="research"))
            with self.assertRaises(EventConflictError):
                store.record(event(event_id="evt-003", task_id="task-002"))

        self.assertEqual(0o700, self.db.parent.stat().st_mode & 0o777)
        self.assertEqual(0o600, self.db.stat().st_mode & 0o777)

    def test_summary_and_task_timeline_aggregate_only_observations(self) -> None:
        records = [
            event(event_id="evt-1"),
            event(
                event_id="evt-2",
                run_id="run-002",
                event_type="review.completed",
                actor="sol",
                emitter="manual-cli",
                model="gpt-5.6-sol",
                reasoning_effort="medium",
                duration_ms=5000,
                input_tokens=1000,
                cached_input_tokens=400,
                output_tokens=200,
                skills=["verification-before-reporting"],
                finding_count=2,
                scope_status="not_checked",
            ),
            event(
                event_id="evt-3",
                run_id="run-003",
                event_type="fix_round.started",
                actor="sol",
                emitter="manual-cli",
                outcome="started",
                model=None,
                reasoning_effort=None,
                duration_ms=None,
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                skills=[],
                fix_round=1,
                finding_count=None,
                scope_status="not_checked",
            ),
            event(
                event_id="evt-4",
                task_id="task-002",
                run_id="run-004",
                event_type="scope.checked",
                actor="system",
                emitter="luna-launcher",
                outcome="failed",
                model=None,
                reasoning_effort=None,
                duration_ms=None,
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                skills=[],
                fix_round=None,
                finding_count=None,
                scope_status="violated",
            ),
        ]
        with EventStore(self.db) as store:
            for record in records:
                store.record(record)
            summary = store.summary()
            tasks = store.tasks(limit=20)
            timeline = store.task_events("task-001")

        self.assertEqual(4, summary["totals"]["events"])
        self.assertEqual(2, summary["totals"]["tasks"])
        self.assertEqual(1, summary["totals"]["delegations"])
        self.assertEqual(1, summary["totals"]["successful_delegations"])
        self.assertEqual(1, summary["totals"]["fix_rounds"])
        self.assertEqual(2, summary["totals"]["review_findings"])
        self.assertEqual(1, summary["totals"]["scope_violations"])
        self.assertEqual(25559, summary["totals"]["input_tokens"])
        self.assertEqual("verification-before-reporting", summary["skills"][0]["skill"])
        self.assertEqual(["task-002", "task-001"], [item["task_id"] for item in tasks])
        self.assertEqual(["evt-1", "evt-2", "evt-3"], [item["event_id"] for item in timeline])

    def test_rejects_unsupported_database_schema(self) -> None:
        self.db.parent.mkdir()
        import sqlite3

        connection = sqlite3.connect(self.db)
        connection.execute("PRAGMA user_version = 99")
        connection.close()
        with self.assertRaises(RuntimeError):
            EventStore(self.db)

    def test_rejects_symlink_database_and_insecure_state_directory(self) -> None:
        real = self.root / "real.sqlite3"
        real.write_bytes(b"")
        self.db.parent.mkdir()
        self.db.symlink_to(real)
        with self.assertRaises(RuntimeError):
            EventStore(self.db)

        self.db.unlink()
        self.db.parent.chmod(0o755)
        with self.assertRaises(RuntimeError):
            EventStore(self.db)

    def test_default_path_uses_xdg_state_without_fixed_home(self) -> None:
        path = default_db_path(
            {"XDG_STATE_HOME": str(self.root / "xdg")}, home=self.root / "home"
        )
        self.assertEqual(self.root / "xdg/codex-observability/events.sqlite3", path)
        with self.assertRaises(RuntimeError):
            default_db_path({"XDG_STATE_HOME": "relative/state"}, home=self.root)


if __name__ == "__main__":
    unittest.main()
