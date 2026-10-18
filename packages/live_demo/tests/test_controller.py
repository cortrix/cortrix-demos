from pathlib import Path
import tempfile
import threading
import unittest

from cortrix_live_demo.server import Controller
from cortrix_live_demo.state import State
from support import make_config


class FakeEngine:
    def __init__(self):
        self.cleaned = []

    def cleanup(self, run_id, path, record):
        self.cleaned.append(path)
        return {
            "path": path,
            "namespace": f"unit-{path}",
            "namespaces_removed": True,
            "postgres_removed": path != "b",
            "original_files_preserved": True,
            "services_preserved": True,
        }

    def cleanup_exports(self, run_id, path):
        return None


class FakeRuntimeManager:
    def __init__(self):
        self.activated = []

    def activate_component(self, component):
        self.activated.append(component)


class ControllerTests(unittest.TestCase):
    def test_code_manifest_uses_only_package_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            config.helpers_root.mkdir(parents=True)
            config.configs_root.mkdir(parents=True)
            (config.helpers_root / "extract_vectors.py").write_text("pass\n")
            (config.configs_root / "cortrix.embedding-only.yaml").write_text("server: {}\n")
            (config.configs_root / "cortrix.full-stack.yaml").write_text("server: {}\n")
            controller = Controller.__new__(Controller)
            controller.config = config
            manifest = controller.code_manifest()
        self.assertIn("src/cortrix_live_demo/server.py", manifest)
        self.assertIn("harness/launch.mjs", manifest)
        self.assertFalse(any(Path(path).is_absolute() for path in manifest))

    def test_cleanup_activates_each_paths_core_component(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            state = State(config.runtime_root, config)
            file = state.add_file("fixture.txt", b"fixture", {"document_id": "fixture"})
            run_id = "run_0123456789abcdef"
            run = {
                "id": run_id,
                "mode": "deterministic",
                "locale": "en-US",
                "state": "completed",
                "created_at": "unit",
                "files": [file],
                "paths": {"a0": {}, "b": {}},
                "events": [],
                "cancel_requested": False,
            }
            state.data["runs"] = [{key: run[key] for key in ("id", "mode", "locale", "state", "created_at")}]
            state.put(run)
            controller = Controller.__new__(Controller)
            controller.state = state
            controller.worker = None
            controller.engine_lock = threading.RLock()
            controller.engine = FakeEngine()
            controller.runtime_manager = FakeRuntimeManager()
            result = controller.cleanup(run_id)
        self.assertEqual(["embedding", "full"], controller.runtime_manager.activated)
        self.assertEqual(["a0", "b"], controller.engine.cleaned)
        self.assertEqual("cleaned", result["state"])


if __name__ == "__main__":
    unittest.main()
