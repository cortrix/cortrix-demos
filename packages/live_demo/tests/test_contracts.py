import json
import os
from pathlib import Path
import unittest

from cortrix_live_demo.config import PACKAGE_ROOT
from cortrix_live_demo.contracts import contract_mapping, validate_fixture_set


class ContractTests(unittest.TestCase):
    def test_public_fixture_copy_and_contract_mapping_are_frozen(self):
        manifest = validate_fixture_set(PACKAGE_ROOT / "runtime-support/fixtures")
        self.assertEqual(manifest["locale"], "en-US")
        self.assertEqual(len(manifest["documents"]), 4)
        mapping = contract_mapping()
        self.assertEqual(mapping["contract_version"], "live_three_path/v1")
        self.assertEqual(mapping["deterministic_paths"], ["a0", "a1", "b"])
        self.assertEqual(mapping["harness_paths"], ["pg", "b"])
        self.assertFalse(mapping["accepted_evidence_allowed"])

    def test_runtime_evidence_schema_and_checkout_cli_are_present(self):
        schema = json.loads((PACKAGE_ROOT / "schemas/run-evidence.schema.json").read_text())
        self.assertEqual("cortrix_live_demo_run_evidence/v1", schema["properties"]["schema"]["const"])
        self.assertEqual({"schema", "manifest", "artifacts"}, set(schema["required"]))
        self.assertIn("cancelling", schema["properties"]["manifest"]["properties"]["state"]["enum"])
        self.assertTrue(os.access(PACKAGE_ROOT / "live-democtl", os.X_OK))
        example = json.loads((PACKAGE_ROOT / "runtime-config.example.json").read_text())
        self.assertFalse(example["allow_external_calls"])
        self.assertTrue(example["internal_bind_host"].startswith("REPLACE_WITH_"))
        self.assertIsNone(example["provider_input_cache_miss_usd_per_million"])
        repository_root = PACKAGE_ROOT.parents[1]
        self.assertIn("packages/live_demo/runtime-config.local.json", (repository_root / ".gitignore").read_text())


if __name__ == "__main__":
    unittest.main()
