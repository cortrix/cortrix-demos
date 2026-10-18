from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from cortrix_demo_runner.catalog import describe_scenario, list_scenarios, load_agent_manifest, require_runnable_scenario, scenario_integration_kind
from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.io import write_json
from cortrix_demo_runner.scenario import validate_scenario


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "order-api-live-three-path"


class LiveScenarioContractTests(unittest.TestCase):
    def test_live_contract_is_deeply_valid_without_acceptance(self) -> None:
        self.assertEqual([], validate_scenario(ROOT, SCENARIO_ID))
        registry = json.loads((ROOT / "scenarios" / "registry.json").read_text(encoding="utf-8"))
        entry = next(item for item in registry["scenarios"] if item["id"] == SCENARIO_ID)
        self.assertEqual("live_three_path_v1", scenario_integration_kind(entry))
        self.assertEqual("candidate", entry["status"])
        self.assertNotIn("technology_profile", entry)
        self.assertNotIn("accepted_pointer", entry)
        self.assertFalse((ROOT / "scenarios" / SCENARIO_ID / "evidence").exists())
        agent = load_agent_manifest(ROOT)
        self.assertEqual("packages/live_demo/manifest.json", agent["catalogs"]["live_demo"])
        self.assertEqual("packages/live_demo/live-democtl", agent["gates"]["live_three_path"]["entrypoint"])

    def test_live_description_is_honest_about_runtime_and_evidence(self) -> None:
        description = describe_scenario(ROOT, SCENARIO_ID)
        self.assertEqual("live_three_path_v1", description["integration_kind"])
        self.assertEqual("candidate", description["scenario"]["status"])
        self.assertEqual("packages/live_demo/manifest.json", description["live_contract"]["runtime_support"])
        self.assertEqual(["a0", "a1", "b"], description["live_contract"]["paths"])
        self.assertEqual(["pg", "b"], description["live_contract"]["harness_paths"])
        self.assertEqual("not_available", description["accepted_evidence"]["status"])
        self.assertIsNone(description["accepted_evidence"]["run_id"])
        self.assertNotIn("technology_profile", description)
        self.assertNotIn("adapter_support", description)

    def test_contract_freezes_paths_stages_operations_and_source_pins(self) -> None:
        contract = json.loads((ROOT / "scenarios" / SCENARIO_ID / "contracts" / "live-three-path.json").read_text(encoding="utf-8"))
        self.assertEqual("live_three_path/v1", contract["contract_version"])
        self.assertEqual(["input", "write", "search", "result", "code"], contract["display_stages"])
        self.assertEqual(["ingest", "query"], contract["business_operations"])
        self.assertEqual(["a0", "a1", "b"], [path["id"] for path in contract["paths"]])
        self.assertEqual(["pg", "b"], [path["id"] for path in contract["harness_paths"]])
        self.assertNotIn("a0", [path["scenario_path"] for path in contract["harness_paths"]])
        for path in contract["paths"]:
            self.assertEqual(contract["display_stages"], [stage["stage"] for stage in path["measurements"]["stage_totals"]])
            self.assertEqual(contract["business_operations"], [step["operation"] for step in path["measurements"]["business_steps"]])
            self.assertTrue(all(stage["duration_ms"] is None for stage in path["measurements"]["stage_totals"]))
            self.assertTrue(all(step["duration_ms"] is None for step in path["measurements"]["business_steps"]))
        self.assertEqual("d298d6b7e64c67551f567e7cddd514bae1adb57b", contract["source_pins"]["cortrix"]["commit"])
        self.assertEqual("99f6f02fecdb7dff40c3fbc9470f5907c29f74ca", contract["source_pins"]["deepseek_harness"]["commit"])
        self.assertIsNone(contract["provider_usage"]["provider_requests"])
        self.assertIsNone(contract["provider_usage"]["cost_estimate_usd"])
        self.assertEqual({"cancel", "resume", "cleanup"}, set(contract["lifecycle"]))
        package = json.loads((ROOT / "packages" / "live_demo" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("implementation_candidate", package["state"])
        self.assertEqual(SCENARIO_ID, package["scenario_id"])
        self.assertFalse(package["external_calls_default"])
        self.assertFalse(package["runtime_results_allowed"])
        self.assertFalse(package["accepted_evidence_allowed"])

    def test_live_validation_rejects_manifest_drift_and_extra_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "scenarios", root / "scenarios")
            contract_path = root / "scenarios" / SCENARIO_ID / "contracts" / "live-three-path.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["unreviewed"] = True
            write_json(contract_path, contract)
            failures = validate_scenario(root, SCENARIO_ID)
            self.assertTrue(any("fields must be exactly" in failure for failure in failures))

            contract.pop("unreviewed")
            contract["input_selection"]["input_manifest_sha256"] = "0" * 64
            write_json(contract_path, contract)
            failures = validate_scenario(root, SCENARIO_ID)
            self.assertTrue(any("checksum" in failure for failure in failures))

    def test_live_validation_rejects_runtime_fixture_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "scenarios", root / "scenarios")
            shutil.copytree(ROOT / "packages" / "live_demo", root / "packages" / "live_demo")
            query = root / "packages" / "live_demo" / "runtime-support" / "fixtures" / "query.txt"
            query.write_text("Changed runtime query\n")
            failures = validate_scenario(root, SCENARIO_ID)
            self.assertTrue(any("Live implementation query checksum mismatch" in failure for failure in failures))

    def test_unknown_integration_kind_fails_closed(self) -> None:
        with self.assertRaises(DemoContractError) as captured:
            scenario_integration_kind({"id": "future", "integration_kind": "future_kind"})
        self.assertEqual("CX_DEMO_SCENARIO_INTEGRATION_UNKNOWN", captured.exception.code)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "scenarios", root / "scenarios")
            registry_path = root / "scenarios" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["scenarios"][0]["integration_kind"] = "future_kind"
            write_json(registry_path, registry)
            with self.assertRaises(DemoContractError):
                list_scenarios(root)

    def test_existing_full_stack_runner_rejects_the_live_candidate(self) -> None:
        with self.assertRaises(DemoContractError) as captured:
            require_runnable_scenario(ROOT, SCENARIO_ID, "full-stack")
        self.assertEqual("CX_DEMO_SCENARIO_RUNTIME_UNSUPPORTED", captured.exception.code)

    def test_bare_validate_deeply_checks_every_registry_entry(self) -> None:
        result = subprocess.run(
            [str(ROOT / "democtl"), "validate"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(["order-api-field-migration", SCENARIO_ID], payload["scenarios"])
        self.assertEqual(0, payload["external_calls"])
        selected = subprocess.run(
            [str(ROOT / "democtl"), "validate", "--scenario", SCENARIO_ID],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, selected.returncode, selected.stderr)
        self.assertEqual(SCENARIO_ID, json.loads(selected.stdout)["scenario"])


if __name__ == "__main__":
    unittest.main()
