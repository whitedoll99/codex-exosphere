from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any


SCHEMA_VERSION = 1
MAX_EVENT_BYTES = 32 * 1024
MAX_LIST_ITEMS = 64
MAX_COUNT = 1_000_000_000
MAX_DURATION_MS = 7 * 24 * 60 * 60 * 1000
MAX_SMALL_COUNT = 1_000_000

FIELDS = {
    "schema_version",
    "event_id",
    "occurred_at",
    "task_id",
    "run_id",
    "event_type",
    "actor",
    "emitter",
    "task_kind",
    "outcome",
    "model",
    "reasoning_effort",
    "duration_ms",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "skills",
    "fix_round",
    "finding_count",
    "scope_status",
    "decision_reason",
}
EVENT_TYPES = {
    "task.started",
    "task.completed",
    "delegation.started",
    "delegation.completed",
    "review.completed",
    "fix_round.started",
    "decision.returned",
    "scope.checked",
}
ACTORS = {"user", "sol", "luna", "reviewer", "system"}
TASK_KINDS = {
    "implementation",
    "review",
    "research",
    "documentation",
    "operations",
    "unknown",
}
OUTCOMES = {
    "started",
    "succeeded",
    "failed",
    "returned",
    "rejected",
    "adopted",
    "partial",
    "unknown",
}
SCOPE_STATUSES = {"passed", "violated", "not_checked"}
DECISION_REASONS = {
    "architecture",
    "compatibility",
    "authorization",
    "scope",
    "security",
    "requirements",
    "work_budget",
    "other",
}
START_EVENTS = {"task.started", "delegation.started", "fix_round.started"}

ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}\Z")
SKILL_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class EventValidationError(ValueError):
    pass


def _exact_fields(value: dict[str, Any]) -> None:
    observed = set(value)
    if observed == FIELDS:
        return
    missing = sorted(FIELDS - observed)
    unknown = sorted(observed - FIELDS)
    raise EventValidationError(f"invalid event fields: missing={missing}, unknown={unknown}")


def _identifier(value: Any, field: str, pattern: re.Pattern[str] = ID_RE) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise EventValidationError(f"{field} must be a bounded ASCII identifier")
    return value


def validate_id(value: Any, field: str = "identifier") -> str:
    """Validate one public task/run/event identifier without event-shaped coupling."""
    return _identifier(value, field, ID_RE)


def _nullable_label(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field, LABEL_RE)


def _nullable_count(value: Any, field: str, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise EventValidationError(f"{field} must be null or an integer from 0 to {maximum}")
    return value


def _timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise EventValidationError("occurred_at must be a canonical UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise EventValidationError("occurred_at must be YYYY-MM-DDTHH:MM:SSZ") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise EventValidationError("occurred_at must be canonical UTC")
    return value


def normalize_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EventValidationError("event must be a JSON object")
    _exact_fields(value)
    if value["schema_version"] != SCHEMA_VERSION:
        raise EventValidationError(f"schema_version must be {SCHEMA_VERSION}")

    normalized = dict(value)
    normalized["event_id"] = validate_id(value["event_id"], "event_id")
    normalized["task_id"] = validate_id(value["task_id"], "task_id")
    normalized["run_id"] = validate_id(value["run_id"], "run_id")
    normalized["emitter"] = _identifier(value["emitter"], "emitter", LABEL_RE)
    normalized["occurred_at"] = _timestamp(value["occurred_at"])

    for field, allowed in (
        ("event_type", EVENT_TYPES),
        ("actor", ACTORS),
        ("task_kind", TASK_KINDS),
        ("outcome", OUTCOMES),
        ("scope_status", SCOPE_STATUSES),
    ):
        if value[field] not in allowed:
            raise EventValidationError(f"{field} has an unsupported value")

    normalized["model"] = _nullable_label(value["model"], "model")
    normalized["reasoning_effort"] = _nullable_label(
        value["reasoning_effort"], "reasoning_effort"
    )
    normalized["duration_ms"] = _nullable_count(
        value["duration_ms"], "duration_ms", MAX_DURATION_MS
    )
    for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
        normalized[field] = _nullable_count(value[field], field, MAX_COUNT)
    normalized["fix_round"] = _nullable_count(
        value["fix_round"], "fix_round", MAX_SMALL_COUNT
    )
    normalized["finding_count"] = _nullable_count(
        value["finding_count"], "finding_count", MAX_SMALL_COUNT
    )
    if normalized["cached_input_tokens"] is not None:
        if normalized["input_tokens"] is None:
            raise EventValidationError("cached_input_tokens requires input_tokens")
        if normalized["cached_input_tokens"] > normalized["input_tokens"]:
            raise EventValidationError("cached_input_tokens exceeds input_tokens")

    skills = value["skills"]
    if not isinstance(skills, list) or len(skills) > MAX_LIST_ITEMS:
        raise EventValidationError(f"skills must contain at most {MAX_LIST_ITEMS} items")
    normalized_skills = [_identifier(item, "skill", SKILL_RE) for item in skills]
    if len(set(normalized_skills)) != len(normalized_skills):
        raise EventValidationError("skills must not contain duplicates")
    normalized["skills"] = sorted(normalized_skills)

    reason = value["decision_reason"]
    if reason is not None and reason not in DECISION_REASONS:
        raise EventValidationError("decision_reason has an unsupported value")
    if value["event_type"] == "decision.returned":
        if value["outcome"] != "returned" or reason is None:
            raise EventValidationError("decision.returned requires returned outcome and reason")
    elif reason is not None:
        raise EventValidationError("decision_reason is only valid for decision.returned")

    if value["event_type"] in START_EVENTS and value["outcome"] != "started":
        raise EventValidationError("started event type requires started outcome")
    if value["event_type"] not in START_EVENTS and value["outcome"] == "started":
        raise EventValidationError("started outcome requires a started event type")
    if value["event_type"] == "scope.checked":
        expected = {"passed": "succeeded", "violated": "failed"}
        if value["scope_status"] not in expected or value["outcome"] != expected[value["scope_status"]]:
            raise EventValidationError("scope.checked outcome and scope_status disagree")
    if value["event_type"] == "review.completed" and normalized["finding_count"] is None:
        raise EventValidationError("review.completed requires finding_count")
    if value["event_type"] != "review.completed" and normalized["finding_count"] is not None:
        raise EventValidationError("finding_count is only valid for review.completed")
    if value["event_type"] == "fix_round.started" and not normalized["fix_round"]:
        raise EventValidationError("fix_round.started requires a positive fix_round")
    return normalized


def parse_event_bytes(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_EVENT_BYTES:
        raise EventValidationError(f"event exceeds {MAX_EVENT_BYTES} bytes")
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventValidationError("event must be valid UTF-8 JSON") from exc
    return normalize_event(value)


def canonical_event_json(event: dict[str, Any]) -> str:
    return json.dumps(normalize_event(event), sort_keys=True, separators=(",", ":"))
