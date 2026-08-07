from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .model import canonical_event_json, normalize_event, validate_id


DB_SCHEMA_VERSION = 1


class EventConflictError(RuntimeError):
    pass


def default_db_path(
    environment: Mapping[str, str] | None = None, *, home: Path | None = None
) -> Path:
    environment = environment if environment is not None else os.environ
    home = (home or Path.home()).resolve()
    state_root = environment.get("XDG_STATE_HOME")
    root = Path(state_root).expanduser() if state_root else home / ".local/state"
    if not root.is_absolute():
        raise RuntimeError("XDG_STATE_HOME must be an absolute path")
    return root / "codex-observability/events.sqlite3"


class EventStore:
    def __init__(self, path: Path) -> None:
        expanded = path.expanduser()
        self.path = Path(os.path.abspath(expanded))
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise RuntimeError(f"refusing unsupported database path: {self.path}")
        if self.path.parent.is_symlink() or (
            self.path.parent.exists() and not self.path.parent.is_dir()
        ):
            raise RuntimeError(f"refusing unsupported database directory: {self.path.parent}")
        parent_missing = not self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent_missing:
            self.path.parent.chmod(0o700)
        if self.path.parent.stat().st_mode & 0o077:
            raise RuntimeError(f"database directory permissions are too broad: {self.path.parent}")
        existed = self.path.exists()
        if existed and self.path.stat().st_mode & 0o077:
            raise RuntimeError(f"database permissions are too broad: {self.path}")
        self.connection = sqlite3.connect(self.path, timeout=5.0)
        if not existed:
            self.path.chmod(0o600)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self._initialize()

    def _initialize(self) -> None:
        version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if version == 0 and tables:
            self.connection.close()
            raise RuntimeError("refusing unversioned non-empty observability database")
        if version not in {0, DB_SCHEMA_VERSION}:
            self.connection.close()
            raise RuntimeError(f"unsupported observability database schema: {version}")
        if version == DB_SCHEMA_VERSION:
            if tables != {"events"}:
                self.connection.close()
                raise RuntimeError("observability database tables do not match schema v1")
            indexes = {
                row[0]
                for row in self.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
                )
            }
            triggers = {
                row[0]
                for row in self.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                )
            }
            if indexes != {"events_task_time", "events_type_time"} or triggers != {
                "events_task_kind_consistent",
                "events_run_task_consistent",
            }:
                self.connection.close()
                raise RuntimeError("observability database objects do not match schema v1")
            return
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    emitter TEXT NOT NULL,
                    task_kind TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    model TEXT,
                    reasoning_effort TEXT,
                    duration_ms INTEGER,
                    input_tokens INTEGER,
                    cached_input_tokens INTEGER,
                    output_tokens INTEGER,
                    fix_round INTEGER,
                    finding_count INTEGER,
                    scope_status TEXT NOT NULL,
                    decision_reason TEXT,
                    normalized_json TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                "CREATE INDEX events_task_time ON events(task_id, occurred_at, sequence)"
            )
            self.connection.execute(
                "CREATE INDEX events_type_time ON events(event_type, occurred_at)"
            )
            self.connection.execute(
                """
                CREATE TRIGGER events_task_kind_consistent
                BEFORE INSERT ON events
                WHEN EXISTS (
                    SELECT 1 FROM events
                    WHERE task_id = NEW.task_id AND task_kind != NEW.task_kind
                )
                BEGIN
                    SELECT RAISE(ABORT, 'task_kind conflict');
                END
                """
            )
            self.connection.execute(
                """
                CREATE TRIGGER events_run_task_consistent
                BEFORE INSERT ON events
                WHEN EXISTS (
                    SELECT 1 FROM events
                    WHERE run_id = NEW.run_id AND task_id != NEW.task_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'run_id conflict');
                END
                """
            )
            self.connection.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def record(self, value: dict[str, Any]) -> bool:
        event = normalize_event(value)
        normalized_json = canonical_event_json(event)
        columns = [
            "event_id", "occurred_at", "task_id", "run_id", "event_type", "actor",
            "emitter", "task_kind", "outcome", "model", "reasoning_effort",
            "duration_ms", "input_tokens", "cached_input_tokens", "output_tokens",
            "fix_round", "finding_count", "scope_status", "decision_reason",
        ]
        values = [event[column] for column in columns]
        inserted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with self.connection:
                self.connection.execute(
                    f"INSERT INTO events ({', '.join(columns)}, normalized_json, inserted_at) "
                    f"VALUES ({', '.join('?' for _ in range(len(columns) + 2))})",
                    [*values, normalized_json, inserted_at],
                )
            return True
        except sqlite3.IntegrityError as exc:
            existing = self.connection.execute(
                "SELECT normalized_json FROM events WHERE event_id = ?", (event["event_id"],)
            ).fetchone()
            if existing is not None and existing[0] == normalized_json:
                return False
            raise EventConflictError(
                f"event conflicts with existing identity: {event['event_id']}"
            ) from exc

    def _totals(self) -> dict[str, int]:
        row = self.connection.execute(
            """
            SELECT
              COUNT(*) AS events,
              COUNT(DISTINCT task_id) AS tasks,
              SUM(event_type = 'delegation.completed') AS delegations,
              SUM(event_type = 'delegation.completed' AND outcome = 'succeeded') AS successful_delegations,
              SUM(event_type = 'delegation.completed' AND outcome = 'failed') AS failed_delegations,
              SUM(event_type = 'fix_round.started') AS fix_rounds,
              COALESCE(SUM(CASE WHEN event_type = 'review.completed' THEN finding_count ELSE 0 END), 0) AS review_findings,
              SUM(scope_status = 'violated') AS scope_violations,
              SUM(event_type = 'decision.returned') AS decision_returns,
              COALESCE(SUM(input_tokens), 0) AS input_tokens,
              COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
              COALESCE(SUM(output_tokens), 0) AS output_tokens,
              COALESCE(SUM(duration_ms), 0) AS duration_ms
            FROM events
            """
        ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    def summary(self) -> dict[str, Any]:
        skills: Counter[str] = Counter()
        for row in self.connection.execute("SELECT normalized_json FROM events"):
            skills.update(json.loads(row[0])["skills"])
        return {
            "schema_version": 1,
            "totals": self._totals(),
            "skills": [
                {"skill": skill, "count": count}
                for skill, count in sorted(skills.items(), key=lambda item: (-item[1], item[0]))
            ],
        }

    def tasks(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be from 1 to 200")
        task_rows = self.connection.execute(
            """
            SELECT task_id, MAX(sequence) AS last_sequence
            FROM events GROUP BY task_id ORDER BY last_sequence DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = []
        for task_row in task_rows:
            task_id = task_row["task_id"]
            row = self.connection.execute(
                """
                SELECT
                  MIN(occurred_at) AS first_occurred_at,
                  MAX(occurred_at) AS last_occurred_at,
                  COUNT(*) AS event_count,
                  SUM(event_type = 'delegation.completed') AS delegations,
                  SUM(event_type = 'fix_round.started') AS fix_rounds,
                  COALESCE(SUM(CASE WHEN event_type = 'review.completed' THEN finding_count ELSE 0 END), 0) AS findings,
                  SUM(scope_status = 'violated') AS scope_violations,
                  COALESCE(SUM(input_tokens), 0) AS input_tokens,
                  COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                  COALESCE(SUM(output_tokens), 0) AS output_tokens,
                  COALESCE(SUM(duration_ms), 0) AS duration_ms
                FROM events WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            latest = self.connection.execute(
                "SELECT task_kind, outcome FROM events WHERE task_id = ? ORDER BY occurred_at DESC, sequence DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            item = {"task_id": task_id, "task_kind": latest["task_kind"], "outcome": latest["outcome"]}
            item.update({key: row[key] for key in row.keys()})
            for key in (
                "event_count", "delegations", "fix_rounds", "findings",
                "scope_violations", "input_tokens", "cached_input_tokens",
                "output_tokens", "duration_ms",
            ):
                item[key] = int(item[key] or 0)
            result.append(item)
        return result

    def task_events(self, task_id: str) -> list[dict[str, Any]]:
        validate_id(task_id, "task_id")
        return [
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT normalized_json FROM events WHERE task_id = ? ORDER BY occurred_at, sequence",
                (task_id,),
            )
        ]
