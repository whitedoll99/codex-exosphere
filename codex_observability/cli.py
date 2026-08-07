from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Sequence

from .model import EventValidationError, parse_event_bytes
from .store import EventConflictError, EventStore, default_db_path


MAX_METRICS_BYTES = 64 * 1024


def _bounded_file(path: Path, *, maximum: int, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise EventValidationError(f"{label} must be a regular non-symlink file")
    if path.stat().st_size > maximum:
        raise EventValidationError(f"{label} exceeds {maximum} bytes")
    return path.read_bytes()


def _db_path(value: Path | None) -> Path:
    return value if value is not None else default_db_path()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _add_db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Content-free local Codex observability")
    commands = parser.add_subparsers(dest="command", required=True)

    emit = commands.add_parser("emit", help="record one strict event v1 JSON file")
    emit.add_argument("--file", type=Path, required=True)
    _add_db(emit)

    luna = commands.add_parser("import-luna", help="map safe Luna launcher metrics to one event")
    luna.add_argument("--metrics", type=Path, required=True)
    luna.add_argument("--task-id", required=True)
    luna.add_argument("--run-id", required=True)
    luna.add_argument("--event-id", required=True)
    luna.add_argument("--occurred-at", required=True)
    luna.add_argument("--task-kind", required=True)
    luna.add_argument("--fix-round", type=int)
    _add_db(luna)

    summary = commands.add_parser("summary", help="show aggregate observations")
    summary.add_argument("--json", action="store_true")
    _add_db(summary)

    tasks = commands.add_parser("tasks", help="list recent observed tasks")
    tasks.add_argument("--limit", type=int, default=50)
    tasks.add_argument("--json", action="store_true")
    _add_db(tasks)

    task = commands.add_parser("task", help="show one task timeline")
    task.add_argument("task_id")
    task.add_argument("--json", action="store_true")
    _add_db(task)

    serve = commands.add_parser("serve", help="serve the authenticated read-only WebUI")
    serve.add_argument("--host", default="0.0.0.0", choices=("0.0.0.0", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=0)
    _add_db(serve)
    return parser


def _record(store: EventStore, event: dict[str, Any]) -> None:
    inserted = store.record(event)
    print(f"{'recorded' if inserted else 'duplicate'} {event['event_id']}")


def _load_luna_metrics(path: Path, arguments: argparse.Namespace) -> dict[str, Any]:
    content = _bounded_file(path, maximum=MAX_METRICS_BYTES, label="metrics")
    try:
        metrics = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventValidationError("metrics must be valid UTF-8 JSON") from exc
    if not isinstance(metrics, dict) or metrics.get("schema_version") != 1:
        raise EventValidationError("unsupported Luna metrics schema")
    status = metrics.get("status")
    if status not in {"succeeded", "failed"}:
        raise EventValidationError("Luna metrics status must be succeeded or failed")
    elapsed = metrics.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0:
        raise EventValidationError("Luna elapsed_seconds must be a non-negative integer")
    usage = metrics.get("usage")
    if not isinstance(usage, dict):
        raise EventValidationError("Luna metrics usage must be an object")
    skills = metrics.get("observed_skills")
    if not isinstance(skills, list):
        raise EventValidationError("Luna observed_skills must be a list")
    scope = metrics.get("scope")
    if scope is None:
        scope_status = "not_checked"
    elif isinstance(scope, dict) and isinstance(scope.get("passed"), bool):
        scope_status = "passed" if scope["passed"] else "violated"
    else:
        raise EventValidationError("Luna scope must be null or contain boolean passed")
    return {
        "schema_version": 1,
        "event_id": arguments.event_id,
        "occurred_at": arguments.occurred_at,
        "task_id": arguments.task_id,
        "run_id": arguments.run_id,
        "event_type": "delegation.completed",
        "actor": "luna",
        "emitter": "luna-launcher",
        "task_kind": arguments.task_kind,
        "outcome": status,
        "model": metrics.get("model"),
        "reasoning_effort": metrics.get("reasoning_effort"),
        "duration_ms": elapsed * 1000,
        "input_tokens": usage.get("input_tokens"),
        "cached_input_tokens": usage.get("cached_input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "skills": skills,
        "fix_round": arguments.fix_round,
        "finding_count": None,
        "scope_status": scope_status,
        "decision_reason": None,
    }


def _human_summary(value: dict[str, Any]) -> str:
    totals = value["totals"]
    lines = [
        f"tasks: {totals['tasks']}",
        f"events: {totals['events']}",
        f"delegations: {totals['delegations']} ({totals['successful_delegations']} succeeded)",
        f"fix rounds: {totals['fix_rounds']}",
        f"review findings: {totals['review_findings']}",
        f"scope violations: {totals['scope_violations']}",
        f"tokens: input={totals['input_tokens']} cached={totals['cached_input_tokens']} output={totals['output_tokens']}",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "emit":
            event = parse_event_bytes(
                _bounded_file(arguments.file, maximum=32 * 1024, label="event")
            )
            with EventStore(_db_path(arguments.db)) as store:
                _record(store, event)
            return 0
        if arguments.command == "import-luna":
            event = _load_luna_metrics(arguments.metrics, arguments)
            with EventStore(_db_path(arguments.db)) as store:
                _record(store, event)
            return 0
        if arguments.command == "summary":
            with EventStore(_db_path(arguments.db)) as store:
                value = store.summary()
            print(_json(value) if arguments.json else _human_summary(value))
            return 0
        if arguments.command == "tasks":
            with EventStore(_db_path(arguments.db)) as store:
                value = store.tasks(limit=arguments.limit)
            if arguments.json:
                print(_json(value))
            else:
                for item in value:
                    print(
                        f"{item['task_id']} {item['task_kind']} {item['outcome']} "
                        f"events={item['event_count']}"
                    )
            return 0
        if arguments.command == "task":
            with EventStore(_db_path(arguments.db)) as store:
                value = store.task_events(arguments.task_id)
            if arguments.json:
                print(_json(value))
            else:
                for item in value:
                    print(
                        f"{item['occurred_at']} {item['event_type']} "
                        f"{item['actor']} {item['outcome']}"
                    )
            return 0
        if arguments.command == "serve":
            from .web import serve

            return serve(_db_path(arguments.db), host=arguments.host, port=arguments.port)
        raise RuntimeError("unsupported command")
    except (
        EventConflictError,
        EventValidationError,
        OSError,
        RuntimeError,
        ValueError,
        sqlite3.Error,
    ) as exc:
        print(f"codex-observe: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
