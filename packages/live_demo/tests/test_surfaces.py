import fcntl
import json
import os
from pathlib import Path
import socket
import threading
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock
import urllib.error
import urllib.request

from cortrix_live_demo.server import Handler, ThreadingHTTPServer, _acquire_runtime_lock, serve


class SurfaceCase(unittest.TestCase):
    surface = "operator"

    def setUp(self):
        self.controller = SimpleNamespace(
            csrf="unit-page-nonce", internal="unit-internal-credential", engine=object(),
            config=SimpleNamespace(operator_origin="http://127.0.0.1:4186"),
            workspace=Mock(return_value={"files": [], "runs": []}),
            create=Mock(return_value={"id": "unit-run"}),
            operation=Mock(return_value={"status": "ready"}),
            tool_projection=Mock(return_value={"projected": True}),
        )
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.controller = self.controller
        self.httpd.surface = self.surface
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.httpd.server_port)
        self.controller.config.operator_origin = self.base

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()

    def request(self, path, body=None, headers=None):
        request = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=headers or {})
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def request_raw(self, path, headers=None):
        request = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers.get_content_type(), response.read()


class OperatorSurfaceTests(SurfaceCase):
    def test_viewer_run_request_matches_the_real_state_contract(self):
        package = Path(__file__).resolve().parents[1]
        html = (package / "viewer" / "index.html").read_text()
        script = (package / "viewer" / "app.js").read_text()
        self.assertIn('<option value="en-US">English sources</option>', html)
        self.assertIn('locale: $("#language").value', script)
        self.assertIn("external_call_authorized: true", script)
        self.assertNotIn("consent: true", script)

    def test_viewer_routes_keep_overview_controls_and_assets_separate(self):
        status, content_type, body = self.request_raw("/")
        self.assertEqual((status, content_type), (200, "text/html"))
        self.assertIn(b'"/demo"', body)
        status, content_type, body = self.request_raw("/demo")
        self.assertEqual((status, content_type), (200, "text/html"))
        self.assertIn(b'data-testid="start-run"', body)
        status, content_type, body = self.request_raw("/assets/capability-layers.png")
        self.assertEqual((status, content_type), (200, "image/png"))
        self.assertGreater(len(body), 1000)

    def test_viewer_asset_route_rejects_path_escape(self):
        self.assertEqual(self.request_raw("/assets/../runtime-config.example.json")[0], 404)

    def test_operator_writes_require_same_origin_and_csrf(self):
        self.assertEqual(self.request("/api/runs", {})[0], 401)
        headers = {"Origin": self.base, "X-CSRF-Token": "unit-page-nonce"}
        self.assertEqual(self.request("/api/runs", {}, headers)[0], 202)

    def test_operator_reads_reject_an_unexpected_host(self):
        for path in ("/api/session", "/api/workspace"):
            self.assertEqual(self.request(path, headers={"Host": "outside.example"})[0], 401)


class InternalSurfaceTests(SurfaceCase):
    surface = "internal"

    def test_internal_surface_exposes_only_authenticated_internal_routes(self):
        for path in ("/", "/api/session", "/api/workspace", "/api/code"):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request("/api/runs", {}, {"Authorization": "Bearer unit-internal-credential"})[0], 404)
        payload = {"run_id": "run_0000000000000000", "path": "pg", "operation": "status", "arguments": {}}
        self.assertEqual(self.request("/internal/harness/tool", payload)[0], 401)
        self.assertEqual(self.request("/internal/harness/tool", payload, {"X-API-Key": "unit-internal-credential"})[0], 401)
        self.assertEqual(self.request("/internal/harness/tool", payload, {"Authorization": "Bearer unit-internal-credential"}), (200, {"projected": True}))
        self.assertEqual(self.request("/healthz"), (200, {"state": "ready", "version": 1}))


class ServeOrderingTests(unittest.TestCase):
    def test_second_service_cannot_acquire_the_same_runtime_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            descriptor = _acquire_runtime_lock(runtime)
            try:
                with self.assertRaisesRegex(RuntimeError, "already owns"):
                    _acquire_runtime_lock(runtime)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
            self.assertEqual([], list(runtime.iterdir()))

    def test_internal_listener_conflict_does_not_mutate_existing_runtime_state(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            access = runtime / "access.json"
            workspace = runtime / "workspace.json"
            access.write_bytes(b'{"credential":"unchanged"}\n')
            workspace.write_bytes(b'{"runs":[{"state":"running"}],"requests":[]}\n')
            before = {path.name: path.read_bytes() for path in (access, workspace)}
            occupied = socket.socket()
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            operator_probe = socket.socket()
            operator_probe.bind(("127.0.0.1", 0))
            operator_port = operator_probe.getsockname()[1]
            operator_probe.close()
            config = SimpleNamespace(
                runtime_root=runtime,
                bind_host="127.0.0.1",
                port=operator_port,
                internal_bind_host="127.0.0.1",
                internal_port=occupied.getsockname()[1],
            )
            try:
                with self.assertRaises(OSError):
                    serve(config, locked=True)
            finally:
                occupied.close()
            self.assertEqual(before, {path.name: path.read_bytes() for path in (access, workspace)})
            self.assertEqual({"access.json", "workspace.json"}, {path.name for path in runtime.iterdir()})


if __name__ == "__main__":
    unittest.main()
