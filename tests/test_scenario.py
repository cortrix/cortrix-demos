from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from cortrix_demo_runner.io import write_json
from cortrix_demo_runner.scenario import load_assertion_contract, load_scenario, validate_scenario


ROOT = Path(__file__).resolve().parents[1]


class ScenarioTests(unittest.TestCase):
    def test_scenario_identity_and_fixture_checksums(self) -> None:
        self.assertEqual([], validate_scenario(ROOT))

    def test_source_identity_is_separate_from_release_identity(self) -> None:
        scenario = load_scenario(ROOT)
        requires = scenario["requires"]
        self.assertEqual("v1.0.0-rc.1", requires["cortrix_release"])
        self.assertNotEqual(requires["cortrix_release_commit"], requires["cortrix_source_revision"])
        self.assertEqual("1.2.0", scenario["scenario_version"])
        self.assertEqual({"query_granularity": "chunk", "document_summary_role": "ingestion_evidence_only"}, scenario["retrieval_contract"])

    def test_layered_ranking_assertions_match_the_reviewed_contract(self) -> None:
        assertions = load_assertion_contract(ROOT)["frozen"]
        self.assertEqual("order-api-release-v2.0", assertions["run_a_dense_cosine_top_document_id"])
        self.assertEqual("order-api-guide-v1.0", assertions["run_b_bge_rerank_leader_document_id"])
        self.assertEqual("order-api-release-v2.0", assertions["run_b_final_top_document_id"])
        self.assertEqual("preserved_final_top1", assertions["resolver_action"])

    def test_scenario_validation_rejects_assertion_and_fixture_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "scenarios", root / "scenarios")
            path = root / "scenarios" / "order-api-field-migration" / "expected" / "assertions.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["frozen"]["run_b_final_top_document_id"] = "missing-document"
            write_json(path, contract)
            self.assertTrue(any("run_b_final_top_document_id" in failure for failure in validate_scenario(root)))

    def test_scenario_validation_rejects_retrieval_contract_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "scenarios", root / "scenarios")
            path = root / "scenarios" / "order-api-field-migration" / "scenario.json"
            scenario = json.loads(path.read_text(encoding="utf-8"))
            scenario["retrieval_contract"]["query_granularity"] = "both"
            write_json(path, scenario)
            self.assertTrue(any("chunk-only" in failure for failure in validate_scenario(root)))

    def test_web_projection_matches_the_reviewed_scenario_contract(self) -> None:
        scenario = load_scenario(ROOT)
        projection = json.loads((ROOT / "scenarios" / "order-api-field-migration" / "web" / "scenario.json").read_text(encoding="utf-8"))
        self.assertEqual(scenario["id"], projection["scenario_id"])
        self.assertEqual(scenario["scenario_version"], projection["scenario_version"])
        self.assertEqual(scenario["retrieval_contract"], projection["retrieval_contract"])

    def test_shared_runner_does_not_hardcode_business_document_identity(self) -> None:
        source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "packages" / "runner" / "src").rglob("*.py"))
        for value in ("order-api-guide-v1.0", "order-api-release-v2.0", "buyer_account_id"):
            self.assertNotIn(value, source)


if __name__ == "__main__":
    unittest.main()
