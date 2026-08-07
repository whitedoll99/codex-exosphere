from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from codex_observability.store import EventStore
from codex_observability.web import create_server
from tests.test_observability_core import event


class ObservabilityWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = self.root / "state/events.sqlite3"
        with EventStore(self.db) as store:
            store.record(event())
        self.token = "test-token-with-at-least-thirty-two-characters"
        self.server = create_server(self.db, host="127.0.0.1", port=0, token=self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temporary.cleanup()

    def request(
        self, path: str, *, token: str | None = None, method: str = "GET"
    ) -> tuple[int, dict[str, str], bytes]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        request = Request(self.base + path, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()
        with response:
            return response.status, dict(response.headers.items()), response.read()

    def test_static_ui_contains_no_token_and_has_security_headers(self) -> None:
        status, headers, body = self.request("/")
        self.assertEqual(200, status)
        self.assertNotIn(self.token.encode(), body)
        self.assertIn(b"Codex Observatory", body)
        self.assertEqual("DENY", headers["X-Frame-Options"])
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

        status, _, script = self.request("/app.js")
        self.assertEqual(200, status)
        self.assertIn(b"Authorization", script)
        self.assertIn(b"history.replaceState", script)
        self.assertIn(b"Luna success", script)
        self.assertIn(b"Decision returns", script)

    def test_api_requires_bearer_and_returns_content_free_data(self) -> None:
        status, headers, body = self.request("/api/v1/summary")
        self.assertEqual(401, status)
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertNotIn(b"task-001", body)

        status, headers, body = self.request("/api/v1/summary", token=self.token)
        self.assertEqual(200, status)
        self.assertEqual("no-store", headers["Cache-Control"])
        value = json.loads(body)
        self.assertEqual(1, value["totals"]["events"])

        status, _, body = self.request("/api/v1/tasks?limit=10", token=self.token)
        self.assertEqual(200, status)
        self.assertEqual("task-001", json.loads(body)[0]["task_id"])

        status, _, body = self.request("/api/v1/tasks/task-001", token=self.token)
        self.assertEqual(200, status)
        self.assertEqual("evt-001", json.loads(body)["events"][0]["event_id"])

    def test_api_rejects_wrong_token_writes_bad_limits_and_unknown_tasks(self) -> None:
        self.assertEqual(401, self.request("/api/v1/summary", token="x" * 40)[0])
        self.assertEqual(405, self.request("/api/v1/summary", token=self.token, method="POST")[0])
        self.assertEqual(405, self.request("/api/v1/summary", token=self.token, method="HEAD")[0])
        self.assertEqual(400, self.request("/api/v1/tasks?limit=201", token=self.token)[0])
        self.assertEqual(400, self.request("/api/v1/tasks?limit=10&limit=20", token=self.token)[0])
        self.assertEqual(404, self.request("/api/v1/tasks/missing", token=self.token)[0])
        self.assertEqual(404, self.request("/../secret", token=self.token)[0])

    def test_server_allows_development_vm_bind_and_rejects_arbitrary_host(self) -> None:
        public = create_server(self.db, host="0.0.0.0", port=0, token=self.token)
        public.server_close()
        with self.assertRaises(ValueError):
            create_server(self.db, host="192.0.2.10", port=0, token=self.token)
        with self.assertRaises(ValueError):
            create_server(self.db, host="127.0.0.1", port=0, token="short")


if __name__ == "__main__":
    unittest.main()
