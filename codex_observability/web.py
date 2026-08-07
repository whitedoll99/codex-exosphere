from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
import socket
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .model import EventValidationError
from .store import EventStore


STATIC_ROOT = Path(__file__).with_name("static")
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32,256}\Z")
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def _handler(db_path: Path, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "CodexObservability/1"
        sys_version = ""

        def log_message(self, _format: str, *_arguments: object) -> None:
            return

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            self.end_headers()

        def _bytes(self, status: int, content_type: str, content: bytes) -> None:
            self._headers(status, content_type, len(content))
            if self.command != "HEAD":
                self.wfile.write(content)

        def _json(self, status: int, value: Any) -> None:
            content = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            self._bytes(status, "application/json; charset=utf-8", content)

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            prefix = "Bearer "
            return supplied.startswith(prefix) and secrets.compare_digest(
                supplied[len(prefix):], token
            )

        def _serve_api(self, parsed: Any) -> None:
            if not self._authorized():
                self._json(401, {"error": "unauthorized"})
                return
            try:
                with EventStore(db_path) as store:
                    if parsed.path == "/api/v1/summary":
                        if parsed.query:
                            self._json(400, {"error": "invalid query"})
                            return
                        self._json(200, store.summary())
                        return
                    if parsed.path == "/api/v1/tasks":
                        query = parse_qs(parsed.query, keep_blank_values=True)
                        if set(query) - {"limit"} or len(query.get("limit", ["50"])) != 1:
                            self._json(400, {"error": "invalid query"})
                            return
                        encoded_limit = query.get("limit", ["50"])[0]
                        if not encoded_limit.isascii() or not encoded_limit.isdigit():
                            self._json(400, {"error": "invalid limit"})
                            return
                        self._json(200, store.tasks(limit=int(encoded_limit)))
                        return
                    prefix = "/api/v1/tasks/"
                    if parsed.path.startswith(prefix) and not parsed.query:
                        task_id = unquote(parsed.path[len(prefix):])
                        events = store.task_events(task_id)
                        if not events:
                            self._json(404, {"error": "not found"})
                            return
                        self._json(200, {"task_id": task_id, "events": events})
                        return
                self._json(404, {"error": "not found"})
            except (EventValidationError, ValueError):
                self._json(400, {"error": "invalid request"})
            except (OSError, RuntimeError, sqlite3.Error):
                self._json(500, {"error": "store unavailable"})

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            parsed = urlsplit(self.path)
            if parsed.path.startswith("/api/"):
                self._serve_api(parsed)
                return
            asset = STATIC_FILES.get(parsed.path)
            if asset is None or parsed.query:
                self._json(404, {"error": "not found"})
                return
            filename, content_type = asset
            try:
                content = (STATIC_ROOT / filename).read_bytes()
            except OSError:
                self._json(500, {"error": "asset unavailable"})
                return
            self._bytes(200, content_type, content)

        def _method_not_allowed(self) -> None:
            self._json(405, {"error": "method not allowed"})

        do_POST = _method_not_allowed
        do_PUT = _method_not_allowed
        do_PATCH = _method_not_allowed
        do_DELETE = _method_not_allowed
        do_HEAD = _method_not_allowed
        do_OPTIONS = _method_not_allowed

    return Handler


def create_server(
    db_path: Path, *, host: str, port: int, token: str
) -> ThreadingHTTPServer:
    if host not in {"0.0.0.0", "127.0.0.1"}:
        raise ValueError("WebUI host must be 0.0.0.0 or 127.0.0.1")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be from 0 to 65535")
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise ValueError("token must be 32 to 256 URL-safe characters")
    server = ThreadingHTTPServer((host, port), _handler(db_path, token))
    server.daemon_threads = True
    return server


def serve(db_path: Path, *, host: str, port: int) -> int:
    token = secrets.token_urlsafe(32)
    server = create_server(db_path, host=host, port=port, token=token)
    bound_host, bound_port = server.server_address
    display_host = socket.gethostname() if bound_host == "0.0.0.0" else bound_host
    print(f"Codex Observatory: http://{display_host}:{bound_port}/#token={token}", flush=True)
    if bound_host == "0.0.0.0":
        print(
            f"If that hostname is not resolvable, replace {display_host!r} with the VM IP.",
            flush=True,
        )
    print("Read-only API; press Ctrl-C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
