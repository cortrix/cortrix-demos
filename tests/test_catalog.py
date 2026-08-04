from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

from cortrix_demo_runner.catalog import describe_scenario, list_scenarios, load_adapter_profile, load_external_call_policy
from cortrix_demo_runner.errors import DemoContractError


ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_agent_can_discover_and_describe_the_accepted_scenario(self) -> None:
        scenarios = list_scenarios(ROOT)
        self.assertEqual(["order-api-field-migration"], [item["id"] for item in scenarios])
        description = describe_scenario(ROOT, "order-api-field-migration")
        self.assertEqual("accepted", description["accepted_evidence"]["status"])
        self.assertEqual("postgresql-pgvector", description["technology_profile"]["baseline"]["adapter_id"])
        self.assertEqual("deepseek-openai-compatible", description["technology_profile"]["llm"]["adapter_id"])
        self.assertEqual(1.0, description["external_call_policy"]["budget_usd"])
        self.assertEqual("discover", description["lifecycle"][0])
        self.assertEqual("cleanup", description["lifecycle"][-1])
        self.assertEqual("required", description["review_gates"]["independent_clean_run"])
        self.assertEqual(["remote_publication"], description["review_gates"]["human_review_required_for"])

    def test_contract_only_adapter_fails_before_runtime_work(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "not implemented") as captured:
            load_adapter_profile(ROOT, "baseline", "elasticsearch", require_implemented=True)
        self.assertEqual("CX_DEMO_ADAPTER_UNSUPPORTED", captured.exception.code)
        self.assertFalse(captured.exception.retryable)

    def test_unknown_scenario_has_a_structured_agent_error(self) -> None:
        with self.assertRaises(DemoContractError) as captured:
            describe_scenario(ROOT, "missing-scenario")
        payload = captured.exception.as_dict()
        self.assertEqual("CX_DEMO_SCENARIO_NOT_FOUND", payload["error"]["code"])
        self.assertEqual("input", payload["error"]["category"])
        self.assertFalse(payload["error"]["retryable"])
        self.assertEqual("missing-scenario", payload["error"]["structured_data"]["scenario_id"])

    def test_external_call_policy_is_fail_closed_at_one_dollar(self) -> None:
        policy = load_external_call_policy(ROOT)
        self.assertEqual(1.0, policy["budget_usd"])
        self.assertFalse(policy["local_generative_fallback_allowed"])

    def test_cli_discovery_and_error_outputs_are_json(self) -> None:
        listing = subprocess.run([str(ROOT / "democtl"), "list", "--json"], cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertEqual("order-api-field-migration", json.loads(listing.stdout)["scenarios"][0]["id"])
        missing = subprocess.run([str(ROOT / "democtl"), "describe", "--scenario", "missing", "--json"], cwd=ROOT, check=False, capture_output=True, text=True)
        self.assertEqual(1, missing.returncode)
        self.assertEqual("CX_DEMO_SCENARIO_NOT_FOUND", json.loads(missing.stderr)["error"]["code"])

    def test_license_logo_and_provenance_are_present(self) -> None:
        self.assertIn("Apache License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / "NOTICE").is_file())
        logo = (ROOT / "assets" / "brand" / "logo-full-dark.svg").read_text(encoding="utf-8")
        self.assertIn("aria-label=\"Cortrix\"", logo)
        self.assertIn("#FF6405", logo)
        self.assertTrue((ROOT / "docs" / "provenance.md").is_file())


if __name__ == "__main__":
    unittest.main()
