from __future__ import annotations

from pathlib import Path
import inspect
import subprocess
import unittest
from unittest.mock import patch

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.runtime import ensure_image, ensure_postgres_schema, load_image_provenance, require_scenario_image_provenance, start


class RuntimeImageTests(unittest.TestCase):
    def test_image_provenance_declares_a_local_source_build(self) -> None:
        provenance = load_image_provenance()
        self.assertEqual("local_source_build", provenance["distribution"])
        self.assertIsNone(provenance["registry_source"])
        self.assertEqual("https://github.com/cortrix/cortrix.git", provenance["source_repository"])
        self.assertEqual("org.opencontainers.image.revision", provenance["required_oci_revision_label"])

    def test_scenario_and_image_provenance_must_match(self) -> None:
        provenance = load_image_provenance()
        requires = {
            "cortrix_release": provenance["cortrix_release"],
            "cortrix_release_commit": provenance["release_commit"],
            "cortrix_source_revision": provenance["source_revision"],
        }
        self.assertEqual(provenance, require_scenario_image_provenance(requires))
        requires["cortrix_source_revision"] = "0" * 40
        with self.assertRaises(DemoContractError) as captured:
            require_scenario_image_provenance(requires)
        self.assertEqual("CX_DEMO_IMAGE_PROVENANCE_MISMATCH", captured.exception.code)

    @patch("cortrix_demo_runner.runtime.subprocess.run")
    def test_live_execution_does_not_hide_an_image_build(self, run: object) -> None:
        run.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="missing")
        with self.assertRaises(DemoContractError) as captured:
            ensure_image(Path(".runtime/cortrix-src"))
        error = captured.exception.as_dict()["error"]
        self.assertEqual("CX_DEMO_IMAGE_MISSING", error["code"])
        self.assertIn("prepare-image", error["structured_data"]["next_action"])
        self.assertEqual(1, run.call_count)

    @patch("cortrix_demo_runner.runtime.subprocess.run")
    def test_prepare_image_builds_only_when_explicitly_enabled(self, run: object) -> None:
        revision = load_image_provenance()["source_revision"]
        run.side_effect = [
            subprocess.CompletedProcess([], 1, stdout="", stderr="missing"),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=f"sha256:{'1' * 64} {revision}\n", stderr=""),
        ]
        result = ensure_image(Path(".runtime/cortrix-src"), build_if_missing=True)
        self.assertEqual("built", result["action"])
        self.assertEqual(revision, result["source_revision"])
        build_command = run.call_args_list[1].args[0]
        self.assertEqual(["docker", "build"], build_command[:2])

    @patch("cortrix_demo_runner.runtime.compose")
    @patch("cortrix_demo_runner.runtime.subprocess.run")
    def test_reused_postgres_volume_reapplies_the_tracked_schema(self, run: object, compose: object) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="ready", stderr="")
        ensure_postgres_schema()
        schema_command = compose.call_args.args[0]
        self.assertIn("ON_ERROR_STOP=1", schema_command)
        self.assertEqual("/docker-entrypoint-initdb.d/10-demo.sql", schema_command[-1])

    def test_start_applies_schema_before_starting_cortrix(self) -> None:
        source = inspect.getsource(start)
        self.assertLess(source.index('compose(["up", "-d", "postgres"]'), source.index("ensure_postgres_schema()"))
        self.assertLess(source.index("ensure_postgres_schema()"), source.index('compose(["up", "-d", "--force-recreate", "cortrix"]'))


if __name__ == "__main__":
    unittest.main()
