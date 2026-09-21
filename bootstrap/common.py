from __future__ import annotations

from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "resident-engineering-patterns"
MARKETPLACE_NAME = "personal"
PLUGIN_SELECTOR = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
PLUGIN_MANIFEST = Path(".codex-plugin") / "plugin.json"
PLUGIN_CACHE_VERSION_RE = re.compile(
    r"^(?P<base>[^+/\\]+)\+codex\."
    r"(?P<cachebuster>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
PLUGIN_ENTRY = {
    "name": PLUGIN_NAME,
    "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
    "category": "development",
}
GENERATED_PATH_NAMES = {"__pycache__", ".pytest_cache"}


@dataclass(frozen=True)
class ManagedTarget:
    source: Path
    destination: Path
    label: str


def managed_targets(home: Path, codex_home: Path) -> list[ManagedTarget]:
    return [
        ManagedTarget(REPO_ROOT / "config" / "AGENTS.md", codex_home / "AGENTS.md", "global AGENTS"),
        ManagedTarget(
            REPO_ROOT / "agents" / "luna_worker.toml",
            codex_home / "agents" / "luna_worker.toml",
            "Luna custom agent",
        ),
        ManagedTarget(
            REPO_ROOT / "agents" / "astra_oracle.toml",
            codex_home / "agents" / "astra_oracle.toml",
            "Astra Oracle custom agent",
        ),
        ManagedTarget(
            REPO_ROOT / "bin" / "run-luna-worker",
            codex_home / "bin" / "run-luna-worker",
            "Luna launcher",
        ),
        ManagedTarget(
            REPO_ROOT / "bin" / "luna-packet-guard",
            codex_home / "bin" / "luna-packet-guard",
            "Luna packet guard",
        ),
        ManagedTarget(
            REPO_ROOT / "bin" / "codex-observe",
            codex_home / "bin" / "codex-observe",
            "Codex observability CLI",
        ),
        ManagedTarget(
            REPO_ROOT / "bin" / "codex-observe-shim",
            home / ".local" / "bin" / "codex-observe",
            "Codex observability PATH shim",
        ),
        ManagedTarget(
            REPO_ROOT / "codex_observability",
            codex_home / "lib" / "codex_observability",
            "Codex observability package",
        ),
        ManagedTarget(
            REPO_ROOT / "plugins" / PLUGIN_NAME,
            home / "plugins" / PLUGIN_NAME,
            "resident engineering plugin",
        ),
    ]


def legacy_uninstall_destinations(codex_home: Path) -> set[Path]:
    """Return retired managed paths accepted only from an existing install state."""
    return {codex_home / "agents" / "terra_reviewer.toml"}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def path_digest(path: Path) -> str:
    if path.is_symlink():
        return sha256_bytes(f"L\0{os.readlink(path)}".encode())
    if path.is_file():
        executable = 1 if path.stat().st_mode & 0o111 else 0
        return sha256_bytes(
            b"F\0" + str(executable).encode() + b"\0" + path.read_bytes()
        )
    if path.is_dir():
        digest = hashlib.sha256(b"D\0")
        for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
            relative = child.relative_to(path).as_posix().encode()
            relative_path = child.relative_to(path)
            if any(part in GENERATED_PATH_NAMES for part in relative_path.parts):
                continue
            if child.suffix in {".pyc", ".pyo"}:
                continue
            digest.update(relative + b"\0" + path_digest(child).encode() + b"\0")
        return digest.hexdigest()
    raise RuntimeError(f"Cannot hash missing or unsupported path: {path}")


def paths_equal(source: Path, destination: Path) -> bool:
    if not destination.exists() and not destination.is_symlink():
        return False
    if source.is_dir() != destination.is_dir():
        return False
    return path_digest(source) == path_digest(destination)


def load_plugin_manifest(plugin_root: Path) -> dict[str, Any]:
    manifest_path = plugin_root / PLUGIN_MANIFEST
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate plugin manifest key: {key}")
            document[key] = value
        return document

    document = json.loads(
        manifest_path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )
    if not isinstance(document, dict):
        raise ValueError(f"plugin manifest must be an object: {manifest_path}")
    return document


def plugin_manifest_without_version(plugin_root: Path) -> str:
    document = load_plugin_manifest(plugin_root)
    version = document.pop("version", None)
    if not isinstance(version, str) or not version:
        raise ValueError("plugin manifest version must be a non-empty string")
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_plugin_base_version(version: Any) -> str:
    if not isinstance(version, str) or not version or "/" in version or "\\" in version:
        raise ValueError("plugin version must be a non-empty path-safe string")
    base = version.split("+", 1)[0]
    if not base:
        raise ValueError("plugin base version must be non-empty")
    return base


def deployed_plugin_base_version(version: Any) -> str:
    if not isinstance(version, str):
        raise ValueError("deployed plugin version must be a string")
    match = PLUGIN_CACHE_VERSION_RE.fullmatch(version)
    if not match:
        raise ValueError("deployed plugin version has an invalid cachebuster suffix")
    return match.group("base")


def plugin_versions_match(source: Path, destination: Path) -> bool:
    try:
        source_base = canonical_plugin_base_version(
            load_plugin_manifest(source).get("version")
        )
        deployed_version = load_plugin_manifest(destination).get("version")
        return deployed_plugin_base_version(deployed_version) == source_base
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _plugin_tree_entries(root: Path) -> dict[Path, Path]:
    entries: dict[Path, Path] = {}
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories if name not in GENERATED_PATH_NAMES
        ]
        for name in directories:
            path = current_path / name
            relative = path.relative_to(root)
            entries[relative] = path
        directories[:] = [
            name for name in directories if not (current_path / name).is_symlink()
        ]
        for name in (
            name for name in files if Path(name).suffix not in {".pyc", ".pyo"}
        ):
            path = current_path / name
            relative = path.relative_to(root)
            entries[relative] = path
    return entries


def _plugin_path_kind(path: Path) -> tuple[str, Any]:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        return "symlink", os.readlink(path)
    if stat.S_ISDIR(mode):
        return "directory", None
    if stat.S_ISREG(mode):
        return "file", bool(mode & 0o111)
    return "other", stat.S_IFMT(mode)


def plugin_paths_equal(
    source: Path,
    destination: Path,
    *,
    ignore_manifest_version: bool = False,
) -> bool:
    """Compare the managed plugin tree, including path and file metadata.

    The version exception is intentionally limited to the plugin's top-level
    manifest. This helper is only for the one managed resident plugin; all
    other managed targets continue to use paths_equal().
    """
    try:
        if (
            _plugin_path_kind(source) != ("directory", None)
            or _plugin_path_kind(destination) != ("directory", None)
        ):
            return False
        source_entries = _plugin_tree_entries(source)
        destination_entries = _plugin_tree_entries(destination)
        if set(source_entries) != set(destination_entries):
            return False
        for relative in source_entries:
            source_path = source_entries[relative]
            destination_path = destination_entries[relative]
            source_kind, source_detail = _plugin_path_kind(source_path)
            destination_kind, destination_detail = _plugin_path_kind(destination_path)
            if source_kind != destination_kind:
                return False
            if source_kind == "symlink":
                if source_detail != destination_detail:
                    return False
            elif source_kind == "file":
                if source_detail != destination_detail:
                    return False
                if (
                    ignore_manifest_version
                    and relative == PLUGIN_MANIFEST
                ):
                    if (
                        plugin_manifest_without_version(source)
                        != plugin_manifest_without_version(destination)
                    ):
                        return False
                elif source_path.read_bytes() != destination_path.read_bytes():
                    return False
            elif source_kind == "other":
                return False
        return True
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return False


def atomic_write(path: Path, content: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def copy_missing(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            temporary.rmdir()
            shutil.copytree(
                source,
                temporary,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "*.pyo"),
            )
            for child in temporary.rglob("*"):
                if child.is_symlink():
                    continue
                if child.is_dir():
                    child.chmod(0o755)
                elif child.is_file():
                    child.chmod(0o755 if child.stat().st_mode & 0o111 else 0o644)
            temporary.chmod(0o755)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return
    mode = 0o755 if source.stat().st_mode & 0o111 else 0o644
    atomic_write(destination, source.read_bytes(), mode)


def default_marketplace() -> dict[str, Any]:
    return {
        "name": MARKETPLACE_NAME,
        "interface": {"displayName": "Personal"},
        "plugins": [],
    }


def load_marketplace(path: Path) -> tuple[dict[str, Any], bytes | None]:
    if not path.exists():
        return default_marketplace(), None
    original = path.read_bytes()
    try:
        document = json.loads(original)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid marketplace JSON at {path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("plugins"), list):
        raise RuntimeError(f"Unexpected marketplace shape at {path}")
    if document.get("name") != MARKETPLACE_NAME:
        raise RuntimeError(
            f"Marketplace {path} is named {document.get('name')!r}, expected {MARKETPLACE_NAME!r}"
        )
    return document, original


def marketplace_status(document: dict[str, Any]) -> str:
    matches = [item for item in document["plugins"] if item.get("name") == PLUGIN_NAME]
    if not matches:
        return "missing"
    if len(matches) == 1 and matches[0] == PLUGIN_ENTRY:
        return "same"
    return "conflict"


def add_marketplace_entry(document: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(document))
    updated["plugins"].append(PLUGIN_ENTRY)
    return updated


def marketplace_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()


def expand_local_path(value: str, home: Path) -> Path:
    if value == "~":
        return home
    if value.startswith("~/"):
        return home / value[2:]
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError(f"Local paths must be absolute or start with ~/: {value!r}")
    return path


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def parse_local_config(path: Path) -> dict[str, Any]:
    """Parse the deliberately small, section-free local config schema."""
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"Cannot read local config {path}: {exc}") from exc
    assignments: list[str] = []
    current: list[str] = []
    bracket_depth = 0
    for raw_line in raw_lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and bracket_depth == 0:
            raise RuntimeError("local config must not contain TOML sections")
        current.append(line)
        bracket_depth += line.count("[") - line.count("]")
        if bracket_depth < 0:
            raise RuntimeError("unbalanced array brackets in local config")
        if bracket_depth == 0:
            assignments.append(" ".join(current))
            current = []
    if current or bracket_depth:
        raise RuntimeError("unterminated array in local config")

    document: dict[str, Any] = {}
    allowed = {"network_access", "trusted_projects", "writable_roots"}
    for assignment in assignments:
        if "=" not in assignment:
            raise RuntimeError(f"invalid local config assignment: {assignment!r}")
        key, encoded = (part.strip() for part in assignment.split("=", 1))
        if key not in allowed:
            raise RuntimeError(f"unknown local config key: {key!r}")
        if key in document:
            raise RuntimeError(f"duplicate local config key: {key!r}")
        if encoded == "true":
            value: Any = True
        elif encoded == "false":
            value = False
        else:
            try:
                value = ast.literal_eval(encoded)
            except (SyntaxError, ValueError) as exc:
                raise RuntimeError(f"invalid value for {key}: {encoded!r}") from exc
        document[key] = value
    return document


def render_config(local_path: Path, home: Path) -> bytes:
    local = parse_local_config(local_path)

    trusted = local.get("trusted_projects", [])
    writable = local.get("writable_roots", [])
    network_access = local.get("network_access", True)
    if not isinstance(trusted, list) or not all(isinstance(item, str) for item in trusted):
        raise RuntimeError("trusted_projects must be an array of strings")
    if not isinstance(writable, list) or not all(isinstance(item, str) for item in writable):
        raise RuntimeError("writable_roots must be an array of strings")
    if not isinstance(network_access, bool):
        raise RuntimeError("network_access must be true or false")

    base = (REPO_ROOT / "config" / "config.base.toml").read_text(encoding="utf-8").rstrip()
    lines = [base, ""]
    for project in trusted:
        expanded = str(expand_local_path(project, home))
        lines.extend([f"[projects.{toml_string(expanded)}]", 'trust_level = "trusted"', ""])
    roots = [str(expand_local_path(item, home)) for item in writable]
    lines.append("[sandbox_workspace_write]")
    lines.append("writable_roots = [")
    lines.extend(f"  {toml_string(root)}," for root in roots)
    lines.append("]")
    lines.append(f"network_access = {'true' if network_access else 'false'}")
    lines.append("")
    return "\n".join(lines).encode()


def forbidden_repository_paths() -> list[Path]:
    forbidden_names = {"auth.json", ".env", "credentials.json", "id_rsa", "id_ed25519"}
    forbidden_suffixes = {".pem", ".key", ".jsonl"}
    findings: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        if path.name in forbidden_names or path.suffix in forbidden_suffixes:
            findings.append(path)
    return findings


def forbidden_repository_content() -> list[tuple[Path, str]]:
    patterns = {
        "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
        "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
        "assigned API credential": re.compile(
            r"(?im)^\s*(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|GITHUB_TOKEN)\s*=\s*[^\s<#][^\s#]{9,}"
        ),
    }
    findings: list[tuple[Path, str]] = []
    for path in REPO_ROOT.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in patterns.items():
            if pattern.search(content):
                findings.append((path, label))
    return findings
