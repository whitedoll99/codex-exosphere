#!/usr/bin/env python3
"""Private, content-bounded continuity storage for a resident Codex."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from typing import Any


PROFILE_ID = "codex-resident"
BUFFER_HEADER = """# Codex diary buffer

<!-- format: hypmem-codex-diary-buffer/v1 -->

This is a host-local, unpublished buffer for first-person diary entries that
may later be submitted to hypmem through `hypmem_diary`.

- Entries are append-only.
- Nothing in this file is recalled or published automatically.
- Do not copy transcripts, prompts, credentials, or raw tool output here.
- A later publisher must require an explicit review and append a receipt only
  after hypmem confirms the write.

## Entry format

```markdown
<!-- hypmem-diary-entry:v1 begin -->
### ENTRY_UUID

- created_at: ISO-8601 UTC
- profile_id: codex-resident
- title: TITLE
- category: CATEGORY_OR_NULL
- importance: INTEGER_1_TO_5
- emotion: FREE_TEXT_OR_NULL

#### Content

FIRST_PERSON_DIARY_CONTENT
<!-- hypmem-diary-entry:v1 end -->
```

The fields `title`, `content`, `category`, `importance`, and `emotion` map
directly to the hypmem diary contract. `entry_id`, `created_at`, and
`profile_id` are local buffer metadata and are not hypmem API fields.

## Publication receipt format

Receipts are appended; existing entries are not rewritten.

```markdown
<!-- hypmem-diary-receipt:v1 begin -->
- entry_id: ENTRY_UUID
- published_at: ISO-8601 UTC
- hypmem_id: DIA_UUID
<!-- hypmem-diary-receipt:v1 end -->
```

## Pending entries
"""
ENTRY_BEGIN = "<!-- hypmem-diary-entry:v1 begin -->"
ENTRY_END = "<!-- hypmem-diary-entry:v1 end -->"
RECEIPT_BEGIN = "<!-- hypmem-diary-receipt:v1 begin -->"
FORBIDDEN_MARKERS = (ENTRY_BEGIN, ENTRY_END, RECEIPT_BEGIN)
MAX_DIRTY_PATHS = 256
MAX_DIRTY_PATH_BYTES = 1000
MAX_FINGERPRINT_BYTES = 64 * 1024 * 1024


class ContinuityError(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_state_root() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "hypmem" / PROFILE_ID


def canonical(path: Path) -> Path:
    if not path.is_absolute():
        raise ContinuityError(f"path_not_absolute: {path}")
    resolved = path.resolve(strict=True)
    if path.is_symlink():
        raise ContinuityError(f"symlink_not_allowed: {path}")
    return resolved


def ensure_private_dir(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise ContinuityError(f"state_dir_untrusted: {path}")
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise ContinuityError(f"state_dir_mode: {path}")
        return
    path.mkdir(mode=0o700, parents=False)


def prepare_state_root(path: Path, *, create: bool) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        raise ContinuityError("state_root_not_absolute")
    if not path.exists() and not create:
        raise ContinuityError("state_unavailable")
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise ContinuityError("state_root_ancestor_untrusted")
    for item in reversed(missing):
        item.mkdir(mode=0o700)
    for item in (path,):
        ensure_private_dir(item)
    return path.resolve(strict=True)


def private_regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ContinuityError(f"private_file_untrusted: {path}")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ContinuityError(f"private_file_mode: {path}")


def read_json_input(source: str, limit: int = 65536) -> dict[str, Any]:
    if source == "-":
        raw = sys.stdin.buffer.read(limit + 1)
    else:
        path = canonical(Path(source).expanduser())
        private_regular(path)
        raw = path.read_bytes()
    if len(raw) > limit:
        raise ContinuityError("input_oversized")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContinuityError("input_invalid_json") from exc
    if not isinstance(value, dict):
        raise ContinuityError("input_not_object")
    return value


def bounded_text(value: Any, field: str, limit: int, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContinuityError(f"{field}_invalid")
    if "\x00" in value or len(value.encode()) > limit:
        raise ContinuityError(f"{field}_invalid")
    if any(marker in value for marker in FORBIDDEN_MARKERS):
        raise ContinuityError(f"{field}_contains_control_marker")
    return value.strip()


def bounded_scalar(value: Any, field: str, limit: int) -> str:
    result = bounded_text(value, field, limit)
    if any(character in result for character in ("\n", "\r", "|")):
        raise ContinuityError(f"{field}_invalid")
    return result


def exact_keys(value: dict[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise ContinuityError("input_schema_mismatch")


def atomic_replace(path: Path, content: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def no_clobber_publish(path: Path, content: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        try:
            os.link(name, path)
        except FileExistsError:
            private_regular(path)
            if path.read_bytes() != content:
                raise ContinuityError("snapshot_conflict")
    finally:
        os.unlink(name)


def initialize_buffer(path: Path) -> None:
    if path.exists() or path.is_symlink():
        private_regular(path)
        if not path.read_text(encoding="utf-8", errors="strict").startswith(
            "# Codex diary buffer\n\n<!-- format: hypmem-codex-diary-buffer/v1 -->"
        ):
            raise ContinuityError("buffer_contract_mismatch")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(BUFFER_HEADER)
        handle.flush()
        os.fsync(handle.fileno())


def append_diary(root: Path, document: dict[str, Any]) -> dict[str, Any]:
    exact_keys(document, {"title", "content", "category", "importance", "emotion"})
    title = bounded_text(document["title"], "title", 160)
    if "\n" in title:
        raise ContinuityError("title_invalid")
    content = bounded_text(document["content"], "content", 12000)
    category = bounded_text(document["category"], "category", 200, nullable=True)
    emotion = bounded_text(document["emotion"], "emotion", 300, nullable=True)
    importance = document["importance"]
    if type(importance) is not int or not 1 <= importance <= 5:
        raise ContinuityError("importance_invalid")
    entry_id = str(uuid.uuid4())
    created_at = now_utc()
    rendered = (
        f"\n\n{ENTRY_BEGIN}\n### {entry_id}\n\n"
        f"- created_at: {created_at}\n- profile_id: {PROFILE_ID}\n"
        f"- title: {title}\n- category: {category or 'null'}\n"
        f"- importance: {importance}\n- emotion: {emotion or 'null'}\n\n"
        f"#### Content\n\n{content}\n{ENTRY_END}\n"
    ).encode()
    path = root / "diary-buffer.md"
    initialize_buffer(path)
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, "ab", closefd=False) as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)
    return {"status": "ok", "entry_id": entry_id, "buffer": str(path), "published": False}


def write_knowledge_index(root: Path, document: dict[str, Any]) -> dict[str, Any]:
    exact_keys(document, {"purpose", "locations", "recent_artifacts", "open_loops"})
    purpose = bounded_text(document["purpose"], "purpose", 2000)
    locations = document["locations"]
    recent = document["recent_artifacts"]
    open_loops = document["open_loops"]
    if not isinstance(locations, list) or not 1 <= len(locations) <= 64:
        raise ContinuityError("locations_invalid")
    if not isinstance(recent, list) or len(recent) > 32:
        raise ContinuityError("recent_artifacts_invalid")
    if not isinstance(open_loops, list) or len(open_loops) > 32:
        raise ContinuityError("open_loops_invalid")

    normalized_locations: list[dict[str, str]] = []
    for item in locations:
        if not isinstance(item, dict):
            raise ContinuityError("locations_invalid")
        exact_keys(item, {"topic", "source", "authority", "freshness"})
        authority = bounded_scalar(item["authority"], "authority", 32)
        freshness = bounded_scalar(item["freshness"], "freshness", 32)
        if authority not in {"normative", "operational", "reference", "subjective"}:
            raise ContinuityError("authority_invalid")
        if freshness not in {"repo_head", "verify_on_rehydrate", "historical", "append_only"}:
            raise ContinuityError("freshness_invalid")
        normalized_locations.append(
            {
                "topic": bounded_scalar(item["topic"], "topic", 300),
                "source": bounded_scalar(item["source"], "source", 1000),
                "authority": authority,
                "freshness": freshness,
            }
        )

    normalized_recent: list[dict[str, str]] = []
    for item in recent:
        if not isinstance(item, dict):
            raise ContinuityError("recent_artifacts_invalid")
        exact_keys(item, {"observed_at", "topic", "source"})
        observed_at = bounded_scalar(item["observed_at"], "observed_at", 32)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", observed_at):
            raise ContinuityError("observed_at_invalid")
        normalized_recent.append(
            {
                "observed_at": observed_at,
                "topic": bounded_scalar(item["topic"], "topic", 300),
                "source": bounded_scalar(item["source"], "source", 1000),
            }
        )
    normalized_open_loops = [bounded_text(item, "open_loops", 1000) for item in open_loops]

    updated_at = now_utc()
    location_rows = "\n".join(
        f"| {item['topic']} | {item['source']} | {item['authority']} | {item['freshness']} |"
        for item in normalized_locations
    )
    recent_rows = (
        "\n".join(
            f"- {item['observed_at']}: {item['topic']} -> {item['source']}"
            for item in normalized_recent
        )
        or "- None"
    )
    loop_rows = "\n".join(f"- {item}" for item in normalized_open_loops) or "- None"
    content = (
        "# Resident Codex knowledge index\n\n"
        "<!-- format: resident-codex-knowledge-index/v1 -->\n\n"
        "This is a pointer-only local index. Referenced artifacts remain the source of truth. "
        "This index grants no authority and must not contain transcripts, prompts, secrets, or "
        "copied memory content.\n\n"
        f"- updated_at: {updated_at}\n"
        f"- profile_id: {PROFILE_ID}\n\n"
        f"## Purpose\n\n{purpose}\n\n"
        "## Knowledge locations\n\n"
        "| Topic | Source | Authority | Freshness |\n"
        "|---|---|---|---|\n"
        f"{location_rows}\n\n"
        f"## Recently saved artifacts\n\n{recent_rows}\n\n"
        f"## Open loops\n\n{loop_rows}\n"
    ).encode()
    path = root / "knowledge-index.md"
    if path.exists() or path.is_symlink():
        private_regular(path)
    atomic_replace(path, content)
    return {
        "status": "ok",
        "index": str(path),
        "updated_at": updated_at,
        "location_count": len(normalized_locations),
        "recent_artifact_count": len(normalized_recent),
        "open_loop_count": len(normalized_open_loops),
    }


def git_output(repo: Path, *arguments: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments], text=True, capture_output=True, check=False
    )
    if result.returncode and not allow_failure:
        raise ContinuityError("git_probe_failed")
    return result.stdout.strip()


def git_bytes(repo: Path, *arguments: str, allow_failure: bool = False) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, check=False
    )
    if result.returncode and not allow_failure:
        raise ContinuityError("git_probe_failed")
    return result.stdout


def hash_git_output(repo: Path, hasher: Any, marker: bytes, *arguments: str) -> None:
    hasher.update(marker)
    process = subprocess.Popen(
        ["git", "-C", str(repo), *arguments], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    total = 0
    assert process.stdout is not None
    try:
        while chunk := process.stdout.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FINGERPRINT_BYTES:
                process.kill()
                process.wait()
                raise ContinuityError("dirty_content_limit_exceeded")
            hasher.update(chunk)
    finally:
        process.stdout.close()
    if process.wait() != 0:
        raise ContinuityError("git_probe_failed")


def git_worktree_state(repo: Path, head: str) -> dict[str, Any]:
    raw_status = git_bytes(
        repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"
    )
    records = [record for record in raw_status.split(b"\0") if record]
    if len(records) > MAX_DIRTY_PATHS:
        raise ContinuityError("dirty_path_limit_exceeded")

    dirty_paths: list[str] = []
    untracked_paths: list[tuple[bytes, str]] = []
    for record in records:
        if len(record) < 4 or record[2:3] != b" ":
            raise ContinuityError("git_status_invalid")
        raw_path = record[3:]
        if len(raw_path) > MAX_DIRTY_PATH_BYTES:
            raise ContinuityError("dirty_path_oversized")
        try:
            path = raw_path.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ContinuityError("dirty_path_not_utf8") from exc
        if not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ContinuityError("dirty_path_invalid")
        dirty_paths.append(path)
        if record[:2] == b"??":
            untracked_paths.append((raw_path, path))

    dirty_paths.sort()
    hasher = hashlib.sha256()
    hasher.update(b"resident-codex-worktree/v1\0")
    for record in sorted(records):
        hasher.update(len(record).to_bytes(8, "big"))
        hasher.update(record)

    if head == "unborn":
        hash_git_output(
            repo,
            hasher,
            b"\0tracked-diff\0",
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            "--",
        )
        hash_git_output(
            repo,
            hasher,
            b"\0staged-diff\0",
            "diff",
            "--cached",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            "--",
        )
    else:
        hash_git_output(
            repo,
            hasher,
            b"\0tracked-diff\0",
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            head,
            "--",
        )

    total_untracked_bytes = 0
    for raw_path, path in sorted(untracked_paths):
        candidate = repo / path
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise ContinuityError("dirty_path_unreadable") from exc
        hasher.update(len(raw_path).to_bytes(8, "big"))
        hasher.update(raw_path)
        hasher.update(stat.S_IFMT(metadata.st_mode).to_bytes(8, "big"))
        if stat.S_ISREG(metadata.st_mode):
            content_hasher = hashlib.sha256()
            try:
                with candidate.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        total_untracked_bytes += len(chunk)
                        if total_untracked_bytes > MAX_FINGERPRINT_BYTES:
                            raise ContinuityError("dirty_content_limit_exceeded")
                        content_hasher.update(chunk)
            except OSError as exc:
                raise ContinuityError("dirty_path_unreadable") from exc
            hasher.update(content_hasher.digest())
        elif stat.S_ISLNK(metadata.st_mode):
            hasher.update(os.fsencode(os.readlink(candidate)))
        else:
            hasher.update(b"non_regular")

    return {
        "dirty": bool(records),
        "dirty_paths": dirty_paths,
        "dirty_path_count": len(dirty_paths),
        "worktree_fingerprint": hasher.hexdigest(),
    }


def git_identity(repo_argument: Path) -> dict[str, Any]:
    repo = canonical(repo_argument.expanduser())
    actual = git_output(repo, "rev-parse", "--show-toplevel")
    if not actual or Path(actual).resolve(strict=True) != repo:
        raise ContinuityError("repo_identity_mismatch")
    head = git_output(repo, "rev-parse", "HEAD", allow_failure=True) or "unborn"
    branch = git_output(repo, "symbolic-ref", "--short", "-q", "HEAD", allow_failure=True) or "detached"
    return {"repo": repo, "head": head, "branch": branch, **git_worktree_state(repo, head)}


def text_list(document: dict[str, Any], field: str) -> list[str]:
    value = document[field]
    if not isinstance(value, list) or len(value) > 32:
        raise ContinuityError(f"{field}_invalid")
    return [bounded_text(item, field, 1000) for item in value]


def repo_state_dir(root: Path, repo: Path, *, create: bool) -> tuple[Path, str]:
    identity = hashlib.sha256(str(repo).encode()).hexdigest()
    continuity = root / "continuity"
    if not continuity.exists():
        if not create:
            raise ContinuityError("handoff_unavailable")
        continuity.mkdir(mode=0o700)
    ensure_private_dir(continuity)
    target = continuity / identity
    if not target.exists():
        if not create:
            raise ContinuityError("handoff_unavailable")
        target.mkdir(mode=0o700)
    ensure_private_dir(target)
    snapshots = target / "handoffs"
    if not snapshots.exists():
        if not create:
            raise ContinuityError("handoff_unavailable")
        snapshots.mkdir(mode=0o700)
    ensure_private_dir(snapshots)
    return target, identity


def render_list(title: str, values: list[str]) -> str:
    body = "\n".join(f"- {item}" for item in values) if values else "- None"
    return f"## {title}\n\n{body}\n"


def write_handoff(root: Path, repo_arg: Path, document: dict[str, Any]) -> dict[str, Any]:
    expected = {"objective", "completed", "pending", "decisions", "blockers", "verification", "files"}
    exact_keys(document, expected)
    objective = bounded_text(document["objective"], "objective", 2000)
    sections = {field: text_list(document, field) for field in expected - {"objective"}}
    identity = git_identity(repo_arg)
    target, repo_hash = repo_state_dir(root, identity["repo"], create=True)
    created_at = now_utc()
    stamp = created_at.replace("-", "").replace(":", "")
    snapshot_name = f"handoff-{stamp}-{identity['head'][:12]}.md"
    content = (
        "# Resident Codex handoff\n\n"
        "<!-- format: resident-codex-handoff/v2 -->\n\n"
        f"- created_at: {created_at}\n- repo_identity: {repo_hash}\n"
        f"- branch: {identity['branch']}\n- head: {identity['head']}\n"
        f"- dirty: {str(identity['dirty']).lower()}\n"
        f"- dirty_path_count: {identity['dirty_path_count']}\n"
        f"- worktree_fingerprint: {identity['worktree_fingerprint']}\n\n"
        + render_list("Dirty paths", identity["dirty_paths"])
        + "\n"
        f"## Objective\n\n{objective}\n\n"
        + render_list("Completed", sections["completed"])
        + "\n" + render_list("Pending", sections["pending"])
        + "\n" + render_list("Decisions", sections["decisions"])
        + "\n" + render_list("Blockers", sections["blockers"])
        + "\n" + render_list("Verification", sections["verification"])
        + "\n" + render_list("Relevant files", sections["files"])
    ).encode()
    snapshot = target / "handoffs" / snapshot_name
    no_clobber_publish(snapshot, content)
    digest = hashlib.sha256(content).hexdigest()
    pointer = {
        "schema_version": 2,
        "repo_identity": repo_hash,
        "snapshot": snapshot_name,
        "sha256": digest,
        "created_at": created_at,
        "branch": identity["branch"],
        "head": identity["head"],
        "dirty": identity["dirty"],
        "dirty_paths": identity["dirty_paths"],
        "dirty_path_count": identity["dirty_path_count"],
        "worktree_fingerprint": identity["worktree_fingerprint"],
    }
    encoded = (json.dumps(pointer, sort_keys=True, separators=(",", ":")) + "\n").encode()
    atomic_replace(target / "latest.json", encoded)
    atomic_replace(target / "CURRENT_WORK.md", content)
    return {"status": "ok", "handoff": str(snapshot), "pointer": str(target / "latest.json"), **pointer}


def latest_handoff(root: Path, repo_arg: Path) -> dict[str, Any]:
    current = git_identity(repo_arg)
    target, repo_hash = repo_state_dir(root, current["repo"], create=False)
    pointer_path = target / "latest.json"
    private_regular(pointer_path)
    try:
        pointer = json.loads(pointer_path.read_bytes())
    except json.JSONDecodeError as exc:
        raise ContinuityError("pointer_invalid") from exc
    required_v1 = {"schema_version", "repo_identity", "snapshot", "sha256", "created_at", "branch", "head", "dirty"}
    required_v2 = required_v1 | {"dirty_paths", "dirty_path_count", "worktree_fingerprint"}
    if (
        not isinstance(pointer, dict)
        or pointer.get("schema_version") not in {1, 2}
        or set(pointer) != (required_v1 if pointer.get("schema_version") == 1 else required_v2)
    ):
        raise ContinuityError("pointer_schema_mismatch")
    if pointer["schema_version"] == 2:
        dirty_paths = pointer["dirty_paths"]
        if (
            not isinstance(dirty_paths, list)
            or len(dirty_paths) > MAX_DIRTY_PATHS
            or any(not isinstance(path, str) or not path for path in dirty_paths)
            or dirty_paths != sorted(dirty_paths)
            or pointer["dirty_path_count"] != len(dirty_paths)
            or not isinstance(pointer["worktree_fingerprint"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", pointer["worktree_fingerprint"])
        ):
            raise ContinuityError("pointer_worktree_state_invalid")
    if pointer["repo_identity"] != repo_hash:
        raise ContinuityError("pointer_repo_mismatch")
    name = pointer["snapshot"]
    if not isinstance(name, str) or Path(name).name != name:
        raise ContinuityError("pointer_snapshot_invalid")
    snapshot = target / "handoffs" / name
    private_regular(snapshot)
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    if digest != pointer["sha256"]:
        raise ContinuityError("handoff_digest_mismatch")
    stale = any((pointer["head"] != current["head"], pointer["branch"] != current["branch"], pointer["dirty"] != current["dirty"]))
    result = {
        "status": "ok",
        "handoff": str(snapshot),
        "verified": True,
        "stale": stale,
        "recorded_head": pointer["head"],
        "recorded_branch": pointer["branch"],
        "recorded_dirty": pointer["dirty"],
        "current_head": current["head"],
        "current_branch": current["branch"],
        "current_dirty": current["dirty"],
        "created_at": pointer["created_at"],
        "pointer_schema_version": pointer["schema_version"],
    }
    if pointer["schema_version"] == 2:
        worktree_changed = pointer["worktree_fingerprint"] != current["worktree_fingerprint"]
        result.update(
            {
                "stale": stale or worktree_changed,
                "worktree_changed": worktree_changed,
                "recorded_dirty_paths": pointer["dirty_paths"],
                "current_dirty_paths": current["dirty_paths"],
                "recorded_dirty_path_count": pointer["dirty_path_count"],
                "current_dirty_path_count": current["dirty_path_count"],
                "recorded_worktree_fingerprint": pointer["worktree_fingerprint"],
                "current_worktree_fingerprint": current["worktree_fingerprint"],
            }
        )
    return result


def status_report(root: Path, repo_arg: Path | None) -> dict[str, Any]:
    buffer = root / "diary-buffer.md"
    pending = receipts = 0
    if buffer.exists() or buffer.is_symlink():
        private_regular(buffer)
        content = buffer.read_text(encoding="utf-8")
        _, separator, records = content.partition("\n## Pending entries\n")
        if not separator:
            raise ContinuityError("buffer_contract_mismatch")
        pending = records.count(ENTRY_BEGIN)
        receipts = records.count(RECEIPT_BEGIN)
    result: dict[str, Any] = {
        "status": "ok",
        "profile_id": PROFILE_ID,
        "buffer": str(buffer),
        "entry_count": pending,
        "receipt_count": receipts,
        "unpublished_upper_bound": max(0, pending - receipts),
    }
    index = root / "knowledge-index.md"
    if index.exists() or index.is_symlink():
        private_regular(index)
        if not index.read_text(encoding="utf-8", errors="strict").startswith(
            "# Resident Codex knowledge index\n\n"
            "<!-- format: resident-codex-knowledge-index/v1 -->"
        ):
            raise ContinuityError("knowledge_index_contract_mismatch")
        result["knowledge_index_present"] = True
    else:
        result["knowledge_index_present"] = False
    result["knowledge_index"] = str(index)
    if repo_arg is not None:
        try:
            result["latest"] = latest_handoff(root, repo_arg)
        except ContinuityError as exc:
            result["latest"] = {"status": "unavailable", "reason": str(exc)}
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--state-root", type=Path, default=default_state_root())
    commands = root.add_subparsers(dest="command", required=True)
    diary = commands.add_parser("append-diary")
    diary.add_argument("--input", required=True)
    index = commands.add_parser("write-index")
    index.add_argument("--input", required=True)
    handoff = commands.add_parser("write-handoff")
    handoff.add_argument("--repo", type=Path, required=True)
    handoff.add_argument("--input", required=True)
    latest = commands.add_parser("latest-handoff")
    latest.add_argument("--repo", type=Path, required=True)
    status = commands.add_parser("status")
    status.add_argument("--repo", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    state_root = prepare_state_root(
        args.state_root, create=args.command in {"append-diary", "write-index", "write-handoff"}
    )
    if args.command == "append-diary":
        result = append_diary(state_root, read_json_input(args.input))
    elif args.command == "write-index":
        result = write_knowledge_index(state_root, read_json_input(args.input))
    elif args.command == "write-handoff":
        result = write_handoff(state_root, args.repo, read_json_input(args.input))
    elif args.command == "latest-handoff":
        result = latest_handoff(state_root, args.repo)
    else:
        result = status_report(state_root, args.repo)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContinuityError, OSError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
