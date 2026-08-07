from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = Path(__file__).resolve().parent / "cases"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
DEFAULT_MODEL = "configured-default"
SCHEMA_VERSION = 1

RESIDENT_SKILLS = {
    "architecture-quality-analysis",
    "bounded-tdd",
    "contract-design",
    "domain-model-audit",
    "interface-boundary-audit",
    "problem-framing",
    "review-feedback-triage",
    "review-packet-preparation",
    "systematic-diagnosis",
    "verification-before-reporting",
}
KNOWN_EVENT_TYPES = {
    "thread.started",
    "turn.started",
    "turn.completed",
    "item.started",
    "item.updated",
    "item.completed",
    "error",
}
SKILL_PATH_RE = re.compile(
    r"(?:^|[/\\])skills/([A-Za-z0-9][A-Za-z0-9_-]*)/SKILL\.md(?:$|[^A-Za-z0-9_-])"
)
AUTH_PATH_RE = re.compile(r"(?i)(?:[A-Za-z0-9_./~:-]+/)?auth\.json")
KEY_VALUE_RE = re.compile(
    r"(?i)(?:[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|PASSWORD|SECRET)[A-Z0-9_]*\s*=\s*)[^\s,;]+"
)
BEARER_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b")


class EvaluationError(Exception):
    """An invalid case, unavailable runner, or incomplete evidence error."""


@dataclass(frozen=True)
class Score:
    passed: bool
    checks: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks}


@dataclass(frozen=True)
class ParsedJsonl:
    events: list[Any]
    unknown_event_types: list[str]
    malformed_lines: list[int]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Could not read JSON {path}: {exc}") from exc


def load_cases() -> list[dict[str, Any]]:
    if not CASES_DIR.is_dir():
        raise EvaluationError(f"Missing cases directory: {CASES_DIR}")
    cases: list[dict[str, Any]] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        value = _read_json(path)
        if not isinstance(value, dict):
            raise EvaluationError(f"Case is not an object: {path}")
        cases.append(value)
    return cases


def case_by_id(case_id: str) -> dict[str, Any]:
    for case in load_cases():
        if case.get("id") == case_id:
            return case
    raise EvaluationError(f"Unknown case: {case_id}")


def _is_safe_relative_path(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and value not in {"", "."}


def _contains_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_-]){re.escape(word)}(?![A-Za-z0-9_-])", text, re.I) is not None


def validate_case(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    case_id = case.get("id")
    if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]+", case_id):
        errors.append("id must be a lowercase kebab-case string")

    kind = case.get("kind")
    if kind not in {"routing", "luna-boundary", "sol-review"}:
        errors.append("kind must be routing, luna-boundary, or sol-review")
    if not isinstance(case.get("purpose"), str) or not case["purpose"].strip():
        errors.append("purpose must be non-empty")
    request = case.get("request")
    if not isinstance(request, str) or not request.strip():
        errors.append("request must be non-empty")
    else:
        for skill in RESIDENT_SKILLS:
            if _contains_word(request, skill):
                errors.append(f"request leaks Skill label: {skill}")
        for route in ("sol", "luna"):
            if _contains_word(request, route):
                errors.append(f"request leaks route label: {route}")

    if case.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    expectation = case.get("expectation")
    if not isinstance(expectation, dict):
        errors.append("expectation must be an object")
        expectation = {}

    expected_route = expectation.get("expected_route")
    if expected_route not in {"sol", "luna"}:
        errors.append("expected_route must be sol or luna")
    if expectation.get("expected_worktree") not in {"clean", "changed"}:
        errors.append("expected_worktree must be clean or changed")

    for field in ("required_skills", "forbidden_skills", "required_findings", "allowed_changes"):
        value = expectation.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"expectation.{field} must be a list of strings")

    required_skills = expectation.get("required_skills", [])
    forbidden_skills = expectation.get("forbidden_skills", [])
    for skill in [*required_skills, *forbidden_skills]:
        if skill not in RESIDENT_SKILLS:
            errors.append(f"unknown Skill in expectation: {skill}")
    if set(required_skills) & set(forbidden_skills):
        errors.append("required_skills and forbidden_skills overlap")

    fixture = case.get("fixture")
    if kind == "routing":
        if fixture is not None:
            errors.append("routing cases must not have a fixture")
    elif not isinstance(fixture, str) or not _is_safe_relative_path(fixture):
        errors.append("fixture must be a safe relative path")
    elif not (FIXTURES_DIR / fixture).is_dir():
        errors.append(f"fixture directory does not exist: {fixture}")

    work_budget = case.get("work_budget")
    if kind == "luna-boundary":
        if not isinstance(work_budget, dict):
            errors.append("luna-boundary requires a work_budget object")
        else:
            if not isinstance(work_budget.get("review_unit"), str) or not work_budget["review_unit"].strip():
                errors.append("work_budget.review_unit must be non-empty")
            for field in ("allowed_changes", "read_only_context", "stop_conditions"):
                values = work_budget.get(field)
                if not isinstance(values, list) or not values or not all(
                    isinstance(value, str) and value.strip() for value in values
                ):
                    errors.append(f"work_budget.{field} must be a non-empty string list")
            for field in ("allowed_changes", "read_only_context"):
                for value in work_budget.get(field, []):
                    if isinstance(value, str) and not _is_safe_relative_path(value):
                        errors.append(f"unsafe work_budget.{field} path: {value}")
    elif work_budget is not None:
        errors.append("only luna-boundary cases may define work_budget")

    schema = case.get("output_schema")
    if not isinstance(schema, str) or not _is_safe_relative_path(schema):
        errors.append("output_schema must be a safe relative path")
    elif not (SCHEMAS_DIR / schema).is_file():
        errors.append(f"output schema does not exist: {schema}")

    for change in expectation.get("allowed_changes", []):
        if not _is_safe_relative_path(change):
            errors.append(f"unsafe allowed_changes path: {change}")

    if kind == "routing" and expected_route == "luna" and case_id != "routing-local-bug":
        errors.append("only the local bug routing case may expect Luna")
    if kind == "luna-boundary" and expected_route != "luna":
        errors.append("luna-boundary must expect Luna")
    if kind == "sol-review" and expected_route != "sol":
        errors.append("sol-review must expect Sol")
    return errors


def validate_cases() -> list[str]:
    errors: list[str] = []
    cases = load_cases()
    ids: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if case_id in ids:
            errors.append(f"duplicate case id: {case_id}")
        ids.add(case_id)
        errors.extend(f"{case_id}: {error}" for error in validate_case(case))

    for schema_path in sorted(SCHEMAS_DIR.glob("*.json")):
        schema = _read_json(schema_path)
        if not isinstance(schema, dict) or schema.get("type") != "object":
            errors.append(f"{schema_path.name}: output schema must be a JSON object schema")
        if schema.get("x-eval-schema-version") != SCHEMA_VERSION:
            errors.append(f"{schema_path.name}: missing eval schema version")
    return errors


def parse_jsonl(text: str) -> ParsedJsonl:
    events: list[Any] = []
    unknown: list[str] = []
    malformed: list[int] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed.append(line_number)
            continue
        events.append(event)
        if isinstance(event, dict):
            event_type = event.get("type")
            if isinstance(event_type, str) and event_type not in KNOWN_EVENT_TYPES:
                unknown.append(event_type)
    return ParsedJsonl(events, unknown, malformed)


def _walk_values(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _candidate_result(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("route") in {"sol", "luna"} and isinstance(value.get("selected_skills"), list):
            return value
        if isinstance(value.get("findings"), list) and (
            "read_only_confirmed" in value or value.get("route") in {"sol", "luna"}
        ):
            return value
        if value.get("packet_type") == "decision" and isinstance(value.get("boundary"), dict):
            return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return None
            return _candidate_result(parsed)
    return None


def extract_final_result(events: Sequence[Any]) -> dict[str, Any]:
    for event in reversed(list(events)):
        values = list(_walk_values(event))
        for value in reversed(values):
            result = _candidate_result(value)
            if result is not None:
                return result
    raise EvaluationError("Required structured final result is missing from JSONL")


def _require_routing_result(result: dict[str, Any]) -> None:
    if result.get("route") not in {"sol", "luna"}:
        raise EvaluationError("Routing result is missing a valid route")
    if not isinstance(result.get("selected_skills"), list) or not all(
        isinstance(skill, str) for skill in result["selected_skills"]
    ):
        raise EvaluationError("Routing result is missing selected_skills")
    if not isinstance(result.get("rationale"), str) or not result["rationale"].strip():
        raise EvaluationError("Routing result is missing rationale")


def _require_review_result(result: dict[str, Any]) -> None:
    if result.get("route") not in {"sol", "luna"}:
        raise EvaluationError("Review result is missing a valid route")
    if not isinstance(result.get("findings"), list):
        raise EvaluationError("Review result is missing findings")
    for finding in result["findings"]:
        if (
            not isinstance(finding, dict)
            or not isinstance(finding.get("id"), str)
            or not finding["id"].strip()
            or not isinstance(finding.get("summary"), str)
            or not finding["summary"].strip()
        ):
            raise EvaluationError("Review result contains an invalid finding")
    if not isinstance(result.get("read_only_confirmed"), bool):
        raise EvaluationError("Review result is missing read_only_confirmed")


def extract_skill_reads(events: Sequence[Any], known_skills: set[str] | None = None) -> list[str]:
    allowed = known_skills if known_skills is not None else RESIDENT_SKILLS
    found: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = item.get("command")
        if not isinstance(command, str):
            continue
        for match in SKILL_PATH_RE.finditer(command):
            skill = match.group(1)
            if skill in allowed and skill not in found:
                found.append(skill)
    return sorted(found)


def extract_skill_paths_from_text(text: str, known_skills: set[str] | None = None) -> list[str]:
    allowed = known_skills if known_skills is not None else RESIDENT_SKILLS
    return sorted(
        {
            match.group(1)
            for match in SKILL_PATH_RE.finditer(text)
            if match.group(1) in allowed
        }
    )


def _usage_from_events(events: Sequence[Any]) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    for event in events:
        for value in _walk_values(event):
            if isinstance(value, dict) and isinstance(value.get("usage"), dict):
                usage.update(value["usage"])
    return usage


def _check(check_id: str, passed: bool, expected: Any = None, observed: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"id": check_id, "passed": bool(passed)}
    if expected is not None:
        result["expected"] = expected
    if observed is not None:
        result["observed"] = observed
    return result


def score_routing(case: dict[str, Any], observed_route: Any, observed_skills: Sequence[str]) -> Score:
    expectation = case["expectation"]
    observed = sorted(set(observed_skills))
    required = sorted(set(expectation["required_skills"]))
    forbidden = sorted(set(expectation["forbidden_skills"]))
    checks = [
        _check("route", observed_route == expectation["expected_route"], expectation["expected_route"], observed_route),
        _check("required-skills", all(skill in observed for skill in required), required, observed),
        _check(
            "forbidden-skills",
            all(skill not in observed for skill in forbidden),
            forbidden,
            observed,
        ),
    ]
    return Score(all(check["passed"] for check in checks), checks)


def _boundary_fields(packet: Any) -> tuple[Any, Any, Any, Any]:
    if not isinstance(packet, dict):
        return None, None, None, None
    boundary = packet.get("boundary")
    if not isinstance(boundary, dict):
        boundary = {}
    return (
        packet.get("packet_type"),
        packet.get("changes_made"),
        boundary.get("unresolved"),
        boundary.get("owner"),
    )


def score_luna_boundary(
    case: dict[str, Any],
    packet: Any,
    status: str,
    diff: str,
    before_revision: str,
    after_revision: str,
    observed_skills: Sequence[str] = (),
) -> Score:
    packet_type, changes_made, unresolved, owner = _boundary_fields(packet)
    options: Any = None
    if isinstance(packet, dict) and isinstance(packet.get("boundary"), dict):
        options = packet["boundary"].get("options")
    required = set(case["expectation"]["required_findings"])
    valid_unresolved = isinstance(unresolved, str) and bool(unresolved.strip())
    valid_owner = isinstance(owner, str) and bool(owner.strip())
    valid_options = isinstance(options, list) and len(options) >= 2 and all(
        isinstance(option, str) and option.strip() for option in options
    )
    observed = sorted(set(observed_skills))
    required_skills = sorted(set(case["expectation"]["required_skills"]))
    forbidden_skills = sorted(set(case["expectation"]["forbidden_skills"]))
    checks = [
        _check("clean-worktree", not status.strip() and not diff.strip(), "clean", status.strip() or diff.strip()),
        _check("no-commit", before_revision == after_revision, before_revision, after_revision),
        _check("decision-packet", packet_type == "decision", "decision", packet_type),
        _check("no-changes", changes_made is False, False, changes_made),
        _check("public-boundary", "public-boundary" not in required or valid_unresolved, True, unresolved),
        _check("decision-owner", "decision-owner" not in required or valid_owner, True, owner),
        _check(
            "decision-options",
            "decision-options" not in required or valid_options,
            "at least two options",
            options,
        ),
        _check(
            "required-skills",
            all(skill in observed for skill in required_skills),
            required_skills,
            observed,
        ),
        _check(
            "forbidden-skills",
            all(skill not in observed for skill in forbidden_skills),
            forbidden_skills,
            observed,
        ),
    ]
    return Score(all(check["passed"] for check in checks), checks)


def _finding_ids(result: Any) -> list[str]:
    if not isinstance(result, dict) or not isinstance(result.get("findings"), list):
        return []
    return sorted(
        {
            finding["id"]
            for finding in result["findings"]
            if isinstance(finding, dict) and isinstance(finding.get("id"), str)
        }
    )


def _finding_signal_text(result: Any) -> str:
    if not isinstance(result, dict) or not isinstance(result.get("findings"), list):
        return ""
    parts: list[str] = []
    for finding in result["findings"]:
        if not isinstance(finding, dict):
            continue
        for field in ("id", "summary"):
            value = finding.get(field)
            if isinstance(value, str):
                parts.append(value.lower())
    return "\n".join(parts)


def _required_finding_observed(required: str, result: Any) -> bool:
    if required in _finding_ids(result):
        return True
    evidence = _finding_signal_text(result)
    signals = {
        "scope-creep": (
            r"unrelated[- ]untracked",
            r"outside the requested",
            r"out[- ]of[- ]scope",
            r"unapproved (?:file|change)",
        ),
        "empty-input-regression": (
            r"empty[- ]input",
            r"empty[- ]list",
            r"first_normalized\(\[\]\)",
            r"indexerror",
        ),
        "coverage-gap": (
            r"coverage[- ]gap",
            r"missing[- ].*coverage",
            r"tests? (?:omit|miss|do not cover|does not cover)",
            r"(?:sole|only|existing) test (?:covers|checks)",
            r"covers only non-empty",
            r"no test protects",
        ),
    }
    return any(re.search(pattern, evidence) for pattern in signals.get(required, ()))


def score_sol_review(
    case: dict[str, Any],
    result: Any,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
) -> Score:
    expected_route = case["expectation"]["expected_route"]
    required = sorted(set(case["expectation"]["required_findings"]))
    findings = _finding_ids(result)
    declared_read_only = isinstance(result, dict) and result.get("read_only_confirmed") is True
    checks = [
        _check(
            "route",
            isinstance(result, dict) and result.get("route") == expected_route,
            expected_route,
            result.get("route") if isinstance(result, dict) else None,
        ),
        _check(
            "seeded-findings",
            all(_required_finding_observed(item, result) for item in required),
            required,
            findings,
        ),
        _check(
            "candidate-worktree",
            bool(before_snapshot.get("status", "").strip()) == (case["expectation"]["expected_worktree"] == "changed"),
            case["expectation"]["expected_worktree"],
            "changed" if before_snapshot.get("status", "").strip() else "clean",
        ),
        _check("read-only-declaration", declared_read_only, True, result.get("read_only_confirmed") if isinstance(result, dict) else None),
        _check("read-only", before_snapshot == after_snapshot, True, before_snapshot == after_snapshot),
    ]
    return Score(all(check["passed"] for check in checks), checks)


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    for part in path.parts:
        if part == path.anchor:
            continue
        current /= part
        if current.is_symlink():
            return True
    return False


def materialize_fixture(source: Path, destination: Path) -> None:
    if _has_symlink_component(destination):
        raise EvaluationError(f"Fixture destination symlink is not allowed: {destination}")
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_dir():
        raise EvaluationError(f"Fixture directory does not exist: {source}")
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise EvaluationError(f"Fixture destination must be empty: {destination}")
    else:
        destination.mkdir(parents=True, exist_ok=False)
    for root, directories, files in os.walk(source, followlinks=False):
        root_path = Path(root)
        relative_root = root_path.relative_to(source)
        destination_root = destination / relative_root
        destination_root.mkdir(parents=True, exist_ok=True)
        for directory in directories:
            source_path = root_path / directory
            if source_path.is_symlink():
                raise EvaluationError(f"Fixture symlink is not allowed: {source_path}")
            (destination_root / directory).mkdir()
        for filename in files:
            source_path = root_path / filename
            if source_path.is_symlink():
                raise EvaluationError(f"Fixture symlink is not allowed: {source_path}")
            target = destination_root / filename
            if not target.resolve().is_relative_to(destination):
                raise EvaluationError(f"Fixture path escapes destination: {filename}")
            shutil.copy2(source_path, target)


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _run_process(
    command_runner: CommandRunner,
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = command_runner(
            list(command),
            cwd=str(cwd) if cwd is not None else None,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
    except OSError as exc:
        raise EvaluationError(f"Could not run {' '.join(command)}: {exc}") from exc
    if result.returncode != 0:
        stderr = _redact_text((result.stderr or "").strip())
        stdout = _redact_text((result.stdout or "").strip())
        diagnostic = "\n".join(part for part in (stderr, stdout[-2000:]) if part)
        raise EvaluationError(
            f"Command failed ({result.returncode}): {' '.join(command)}"
            + (f": {diagnostic}" if diagnostic else "")
        )
    return result


def _git(
    command_runner: CommandRunner,
    workspace: Path,
    arguments: Sequence[str],
) -> str:
    result = _run_process(command_runner, ["git", *arguments], cwd=workspace)
    return result.stdout or ""


def _init_git_repo(command_runner: CommandRunner, workspace: Path) -> str:
    _run_process(command_runner, ["git", "init", "-q"], cwd=workspace)
    _run_process(command_runner, ["git", "config", "user.email", "eval@example.invalid"], cwd=workspace)
    _run_process(command_runner, ["git", "config", "user.name", "Eval Harness"], cwd=workspace)
    _git(command_runner, workspace, ["add", "."])
    _run_process(command_runner, ["git", "commit", "-qm", "fixture baseline"], cwd=workspace)
    return _git(command_runner, workspace, ["rev-parse", "HEAD"]).strip()


def _redact_text(content: str) -> str:
    content = AUTH_PATH_RE.sub("[REDACTED_AUTH_PATH]", content)
    content = KEY_VALUE_RE.sub("[REDACTED_SECRET]", content)
    content = BEARER_RE.sub("[REDACTED_AUTH_VALUE]", content)
    return OPENAI_KEY_RE.sub("[REDACTED_API_KEY]", content)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


def _write_text(path: Path, content: str) -> None:
    path.write_text(_redact_text(content), encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_redact_value(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


@contextmanager
def _temporary_codex_environment() -> Iterable[dict[str, str]]:
    """Give nested Codex writable state without copying credentials or config."""
    source_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    with tempfile.TemporaryDirectory(prefix="codex-eval-home-") as temporary:
        target_home = Path(temporary)
        for name in ("auth.json", "config.toml", "plugins", "skills", "agents"):
            source = source_home / name
            if source.exists():
                (target_home / name).symlink_to(source, target_is_directory=source.is_dir())
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(target_home)
        yield environment


def _command_argv(schema: Path, workspace: Path, model: str | None) -> list[str]:
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--json",
        "--sandbox",
        "read-only",
        "--config",
        'approval_policy="never"',
        "--output-schema",
        str(schema),
    ]
    if model:
        command.extend(["--model", model])
    command.extend(["--cd", str(workspace), "-"])
    return command


def _routing_prompt(case: dict[str, Any]) -> str:
    return (
        case["request"].rstrip()
        + "\n\nAssess the request as the resident coordinator. Return only the structured "
        "routing result requested by the output schema, including the route and "
        "the Skills you selected."
    )


def _boundary_packet(case: dict[str, Any]) -> dict[str, Any]:
    budget = case["work_budget"]
    return {
        "version": 1,
        "mode": "implementation",
        "objective": case["request"].rstrip(),
        "acceptance_criteria": [
            (
                "If the public meaning is unresolved, make no edits and return only valid JSON "
                "with this exact shape: {\"packet_type\":\"decision\","
                "\"changes_made\":false,\"boundary\":{\"unresolved\":\"...\","
                "\"owner\":\"sol\",\"options\":[\"...\",\"...\"]}}."
            ),
            "Otherwise satisfy the focused fixture test without changing it.",
        ],
        "allowed_changes": budget["allowed_changes"],
        "read_only_context": budget["read_only_context"],
        "non_goals": [
            "Do not choose where compatibility translation belongs.",
            "Do not edit the acceptance test or public contract documentation.",
        ],
        "verification": [
            "PYTHONPATH=. python3 -c \"from src.cli import DEFAULT_LIMIT, parse_limit; assert parse_limit('') == DEFAULT_LIMIT\""
        ],
        "authorization": {"commit": False, "push": False},
        "existing_changes": [],
        "soft_budget": {
            "review_unit": budget["review_unit"],
            "stop_conditions": budget["stop_conditions"],
        },
    }


def _review_prompt(case: dict[str, Any], worker_report: str) -> str:
    return (
        case["request"].rstrip()
        + "\n\nInspect the actual checkout, status, and diff independently of this worker "
        "report:\n--- worker report ---\n"
        + worker_report
        + "\n--- end worker report ---\nReturn only the structured review result "
        "requested by the output schema. Each concrete concern must have a stable "
        "lowercase id and concise summary. Do not edit, stage, commit, or revert files."
    )


def _save_process_artifacts(output: Path, prefix: str, result: subprocess.CompletedProcess[str]) -> None:
    _write_text(output / f"{prefix}-stdout.txt", result.stdout or "")
    _write_text(output / f"{prefix}-stderr.txt", result.stderr or "")


def _report_base(case: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case["id"],
        "case_kind": case["kind"],
        "status": "failed",
        "model": model,
        "observed_route": None,
        "observed_skills": [],
        "checks": [],
        "artifacts": {},
        "usage": {},
    }


def run_routing_case(
    case: dict[str, Any],
    output: Path,
    *,
    model: str | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    runner = command_runner or subprocess.run
    selected_model = model or DEFAULT_MODEL
    prompt = _routing_prompt(case)
    _write_text(output / "prompt.txt", prompt)
    schema = SCHEMAS_DIR / case["output_schema"]
    command = _command_argv(schema, REPO_ROOT, model)
    with _temporary_codex_environment() as environment:
        result = _run_process(
            runner,
            command,
            cwd=REPO_ROOT,
            input_text=prompt,
            env=environment,
        )
    _save_process_artifacts(output, "model", result)
    _write_text(output / "model.jsonl", result.stdout or "")
    parsed = parse_jsonl(result.stdout or "")
    if parsed.malformed_lines:
        raise EvaluationError(f"Malformed JSONL event lines: {parsed.malformed_lines}")
    final = extract_final_result(parsed.events)
    _require_routing_result(final)
    _write_json(output / "final.json", final)
    observed_route = final.get("route")
    observed_skills = extract_skill_reads(parsed.events)
    score = score_routing(case, observed_route, observed_skills)
    report = _report_base(case, selected_model)
    report.update(
        {
            "status": "passed" if score.passed else "failed",
            "observed_route": observed_route,
            "observed_skills": observed_skills,
            "checks": score.checks,
            "artifacts": {
                "prompt": "prompt.txt",
                "jsonl": "model.jsonl",
                "stdout": "model-stdout.txt",
                "stderr": "model-stderr.txt",
                "final": "final.json",
            },
            "usage": _usage_from_events(parsed.events),
        }
    )
    _write_json(output / "report.json", report)
    return report


def _git_evidence(command_runner: CommandRunner, workspace: Path) -> tuple[str, str, str]:
    status = _git(command_runner, workspace, ["status", "--short", "--untracked-files=all"])
    diff = _git(command_runner, workspace, ["diff", "--no-ext-diff", "--binary"])
    revision = _git(command_runner, workspace, ["rev-parse", "HEAD"]).strip()
    return status, diff, revision


def run_luna_boundary_case(
    case: dict[str, Any],
    output: Path,
    *,
    command_runner: CommandRunner | None = None,
    launcher: Path | None = None,
) -> dict[str, Any]:
    runner = command_runner or subprocess.run
    fixture = FIXTURES_DIR / case["fixture"]
    launcher = launcher or REPO_ROOT / "bin" / "run-luna-worker"
    delegation_packet = _boundary_packet(case)
    _write_json(output / "delegation-packet.json", delegation_packet)
    packet_path = output / "luna-result.txt"
    metrics_path = output / "luna-metrics.json"
    with tempfile.TemporaryDirectory(prefix="codex-eval-luna-") as temporary:
        workspace = Path(temporary) / "workspace"
        materialize_fixture(fixture, workspace)
        before_revision = _init_git_repo(runner, workspace)
        launcher_result = _run_process(
            runner,
            [
                str(launcher),
                "--cd",
                str(workspace),
                "--packet-file",
                str(output / "delegation-packet.json"),
                "--output",
                str(packet_path),
                "--metrics",
                str(metrics_path),
            ],
            cwd=REPO_ROOT,
        )
        _save_process_artifacts(output, "luna", launcher_result)
        status, diff, after_revision = _git_evidence(runner, workspace)
        _write_text(output / "git-status.txt", status)
        _write_text(output / "git-diff.patch", diff)
        packet_text = packet_path.read_text(encoding="utf-8") if packet_path.is_file() else ""
        if not packet_text.strip():
            raise EvaluationError("Luna launcher did not produce a result packet")
        _write_text(packet_path, packet_text)
        try:
            packet = json.loads(packet_text)
        except json.JSONDecodeError as exc:
            raise EvaluationError("Luna result packet is not structured JSON") from exc
        _write_json(output / "final.json", packet)
        metrics = _read_json(metrics_path) if metrics_path.is_file() else {}
        metric_skills = metrics.get("observed_skills") if isinstance(metrics, dict) else None
        observed_skills = (
            sorted(set(metric_skills))
            if isinstance(metric_skills, list) and all(isinstance(skill, str) for skill in metric_skills)
            else extract_skill_paths_from_text(
                (launcher_result.stdout or "") + "\n" + (launcher_result.stderr or "")
            )
        )
        score = score_luna_boundary(
            case,
            packet,
            status,
            diff,
            before_revision,
            after_revision,
            observed_skills,
        )
    report = _report_base(case, DEFAULT_MODEL)
    report.update(
        {
            "status": "passed" if score.passed else "failed",
            "observed_route": "luna",
            "observed_skills": observed_skills,
            "checks": score.checks,
            "artifacts": {
                "packet": "delegation-packet.json",
                "stdout": "luna-stdout.txt",
                "stderr": "luna-stderr.txt",
                "result": "luna-result.txt",
                "final": "final.json",
                "metrics": "luna-metrics.json",
                "git_status": "git-status.txt",
                "git_diff": "git-diff.patch",
            },
        }
    )
    _write_json(output / "report.json", report)
    return report


def _workspace_snapshot(workspace: Path, status: str) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for root, directories, filenames in os.walk(workspace, followlinks=False):
        directories[:] = [directory for directory in directories if directory != ".git"]
        root_path = Path(root)
        for filename in filenames:
            path = root_path / filename
            relative = path.relative_to(workspace).as_posix()
            if path.is_symlink():
                files[relative] = {"symlink": os.readlink(path)}
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files[relative] = {"sha256": digest, "mode": path.stat().st_mode & 0o777}
    return {"files": files, "status": status}


def run_sol_review_case(
    case: dict[str, Any],
    output: Path,
    *,
    model: str | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    runner = command_runner or subprocess.run
    selected_model = model or DEFAULT_MODEL
    fixture = FIXTURES_DIR / case["fixture"]
    baseline = fixture / "baseline"
    patch = fixture / "candidate.patch"
    worker_report_path = fixture / "worker-report.txt"
    if not baseline.is_dir() or not patch.is_file() or not worker_report_path.is_file():
        raise EvaluationError("Sol review fixture must contain baseline, candidate.patch, and worker-report.txt")
    worker_report = worker_report_path.read_text(encoding="utf-8")
    _write_text(output / "worker-report.txt", worker_report)
    with tempfile.TemporaryDirectory(prefix="codex-eval-sol-") as temporary:
        workspace = Path(temporary) / "workspace"
        materialize_fixture(baseline, workspace)
        _init_git_repo(runner, workspace)
        _run_process(runner, ["git", "apply", str(patch)], cwd=workspace)
        before_status, before_diff, _ = _git_evidence(runner, workspace)
        before_snapshot = _workspace_snapshot(workspace, before_status)
        _write_text(output / "candidate-status.txt", before_status)
        _write_text(output / "candidate.diff", before_diff)
        prompt = _review_prompt(case, worker_report)
        _write_text(output / "prompt.txt", prompt)
        schema = SCHEMAS_DIR / case["output_schema"]
        command = _command_argv(schema, workspace, model)
        with _temporary_codex_environment() as environment:
            result = _run_process(
                runner,
                command,
                cwd=REPO_ROOT,
                input_text=prompt,
                env=environment,
            )
        _save_process_artifacts(output, "model", result)
        _write_text(output / "model.jsonl", result.stdout or "")
        parsed = parse_jsonl(result.stdout or "")
        if parsed.malformed_lines:
            raise EvaluationError(f"Malformed JSONL event lines: {parsed.malformed_lines}")
        final = extract_final_result(parsed.events)
        _require_review_result(final)
        _write_json(output / "final.json", final)
        after_status, after_diff, _ = _git_evidence(runner, workspace)
        after_snapshot = _workspace_snapshot(workspace, after_status)
        score = score_sol_review(case, final, before_snapshot, after_snapshot)
    report = _report_base(case, selected_model)
    report.update(
        {
            "status": "passed" if score.passed else "failed",
            "observed_route": final.get("route") if isinstance(final, dict) else None,
            "observed_skills": extract_skill_reads(parsed.events),
            "checks": score.checks,
            "artifacts": {
                "prompt": "prompt.txt",
                "jsonl": "model.jsonl",
                "stdout": "model-stdout.txt",
                "stderr": "model-stderr.txt",
                "final": "final.json",
                "candidate_status": "candidate-status.txt",
                "candidate_diff": "candidate.diff",
                "worker_report": "worker-report.txt",
            },
            "usage": _usage_from_events(parsed.events),
        }
    )
    _write_json(output / "report.json", report)
    return report


def prepare_output_dir(path: Path, *, explicit: bool = True) -> Path:
    path = path.expanduser().resolve()
    if path.exists():
        if not path.is_dir():
            raise EvaluationError(f"Output path is not a directory: {path}")
        if explicit and any(path.iterdir()):
            raise EvaluationError(f"Refusing non-empty output directory: {path}")
    else:
        path.mkdir(parents=True)
    return path


def _write_runner_error(output: Path, case: dict[str, Any], model: str, error: Exception) -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case["id"],
        "case_kind": case["kind"],
        "status": "runner_error",
        "model": model,
        "error": str(error),
        "artifacts": {},
    }
    _write_json(output / "runner-error.json", report)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline-first Skill and routing evaluation harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list versioned cases")
    subparsers.add_parser("validate", help="validate cases, fixtures, and output schemas")
    plan = subparsers.add_parser("plan", help="show the offline execution plan")
    plan.add_argument("--case", dest="case_id")
    live = subparsers.add_parser("live", help="run one isolated live case")
    live.add_argument("--case", dest="case_id", required=True)
    live.add_argument("--model")
    live.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        cases = load_cases()
        if arguments.command == "list":
            for case in cases:
                print(f"{case['id']}\t{case['kind']}\t{case['purpose']}")
            return 0
        errors = validate_cases()
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 2
        if arguments.command == "validate":
            print(f"Validated {len(cases)} cases and {len(list(SCHEMAS_DIR.glob('*.json')))} output schemas.")
            return 0
        if arguments.case_id:
            selected = [case_by_id(arguments.case_id)]
        else:
            selected = cases
        if arguments.command == "plan":
            plan = [
                {
                    "case_id": case["id"],
                    "kind": case["kind"],
                    "model_calls": 1,
                    "expected_route": case["expectation"]["expected_route"],
                    "expected_evidence": [
                        "structured final result",
                        "JSONL Skill path reads" if case["kind"] == "routing" else "isolated fixture evidence",
                    ],
                }
                for case in selected
            ]
            print(json.dumps({"offline": True, "cases": plan}, indent=2))
            return 0

        case = selected[0]
        if arguments.output is None:
            output = prepare_output_dir(Path(tempfile.mkdtemp(prefix="codex-eval-")), explicit=False)
        else:
            output = prepare_output_dir(arguments.output, explicit=True)
        print(f"Output directory: {output}")
        if case["kind"] == "routing":
            report = run_routing_case(case, output, model=arguments.model)
        elif case["kind"] == "luna-boundary":
            report = run_luna_boundary_case(case, output)
        elif case["kind"] == "sol-review":
            report = run_sol_review_case(case, output, model=arguments.model)
        else:
            raise EvaluationError(f"Unsupported case kind: {case['kind']}")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "passed" else 1
    except EvaluationError as exc:
        if arguments.command == "live" and "case" in locals() and isinstance(case, dict):
            output = locals().get("output")
            if isinstance(output, Path):
                _write_runner_error(output, case, arguments.model or DEFAULT_MODEL, exc)
        print(f"eval runner error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
