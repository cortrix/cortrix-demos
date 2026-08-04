from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest

from cortrix_demo_runner.catalog import describe_scenario, list_scenarios, load_adapter_profile, load_agent_manifest, load_external_call_policy
from cortrix_demo_runner.errors import DemoContractError


ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_first_time_agent_has_a_safe_root_bootstrap(self) -> None:
        manifest = load_agent_manifest(ROOT)
        self.assertEqual("accepted_replay", manifest["agent_first"]["default_mode"])
        self.assertFalse(manifest["agent_first"]["default_external_calls"])
        self.assertTrue(manifest["agent_first"]["fail_closed"])
        self.assertEqual(
            [
                "./democtl list --json",
                "./democtl describe --scenario order-api-field-migration --json",
                "./democtl validate --scenario order-api-field-migration",
                "./democtl verify-accepted",
            ],
            manifest["bootstrap"]["safe_default"],
        )
        instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Agent Bootstrap", instructions)
        for command in manifest["bootstrap"]["safe_default"]:
            self.assertIn(command, instructions)

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
        accepted = subprocess.run([str(ROOT / "democtl"), "verify-accepted"], cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertEqual("pass", json.loads(accepted.stdout)["status"])
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

    def test_human_run_guides_and_repository_structure_are_discoverable(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Agent-first by design", readme)
        self.assertIn("## How the repository is organized", readme)
        for relative_path in (
            "scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector.md",
            "scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack.md",
            "scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector-step-by-step.md",
            "scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack-step-by-step.md",
        ):
            self.assertIn(relative_path, readme)
            self.assertTrue((ROOT / relative_path).is_file())
        run_a = (ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-a-postgresql-pgvector.md").read_text(encoding="utf-8")
        run_b = (ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-b-cortrix-full-stack.md").read_text(encoding="utf-8")
        numbered_heading = re.compile(r"^## [0-9]+\. ")
        self.assertEqual(
            [line for line in run_a.splitlines() if numbered_heading.match(line)],
            [line for line in run_b.splitlines() if numbered_heading.match(line)],
        )
        self.assertIn("The combined workflow executes Run A first and Run B second", run_a)
        self.assertIn("The combined workflow executes Run A first and Run B second", run_b)
        self.assertIn("`account_id`", run_a)
        self.assertIn("`buyer_account_id`", run_b)
        self.assertIn("independent Clean Run acceptance", run_b)
        run_a_pipeline = (ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-a-postgresql-pgvector-step-by-step.md").read_text(encoding="utf-8")
        run_b_pipeline = (ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-b-cortrix-full-stack-step-by-step.md").read_text(encoding="utf-8")
        manual_heading = re.compile(r"^## [0-9]+\. ")
        self.assertEqual(
            [line for line in run_a_pipeline.splitlines() if manual_heading.match(line)],
            [line for line in run_b_pipeline.splitlines() if manual_heading.match(line)],
        )
        self.assertNotIn("./democtl", run_a_pipeline)
        self.assertNotIn("./democtl", run_b_pipeline)
        query_command = "python3 -c 'from pathlib import Path; print(Path(\"scenarios/order-api-field-migration/fixtures/query.txt\").read_text().strip())'"
        self.assertIn(query_command, run_a_pipeline)
        self.assertIn(query_command, run_b_pipeline)
        for fragment in ("docker-compose", "psql -X", "embedding <=>", "extract_vectors.py", "/documents/tasks/", "/progress"):
            self.assertIn(fragment, run_a_pipeline)
        for fragment in ("cortrix.full-stack.yaml", "/documents", "/query?explain=true", "deepseek-v4-flash", "inspect_namespace.py"):
            self.assertIn(fragment, run_b_pipeline)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Demo observability versus production operation", readme)
        self.assertIn("not a required Cortrix production interface", readme)
        self.assertIn("Humans can use the paired manual Runbooks", readme)


if __name__ == "__main__":
    unittest.main()
