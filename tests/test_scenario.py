from __future__ import annotations

import json
from pathlib import Path
import unittest

from cortrix_demo_runner.scenario import load_scenario, validate_scenario


ROOT = Path(__file__).resolve().parents[1]


class ScenarioTests(unittest.TestCase):
    def test_scenario_identity_and_fixture_checksums(self) -> None:
        self.assertEqual([], validate_scenario(ROOT))

    def test_source_identity_is_separate_from_release_identity(self) -> None:
        scenario = load_scenario(ROOT)
        requires = scenario["requires"]
        self.assertEqual("v1.0.0-rc.1", requires["cortrix_release"])
        self.assertNotEqual(requires["cortrix_release_commit"], requires["cortrix_source_revision"])
        self.assertEqual("1.1.0", scenario["scenario_version"])

    def test_layered_ranking_assertions_match_the_reviewed_contract(self) -> None:
        assertions = json.loads((ROOT / "scenarios" / "order-api-field-migration" / "expected" / "assertions.json").read_text(encoding="utf-8"))["frozen"]
        self.assertEqual("order-api-release-v2.0", assertions["run_a_dense_cosine_top_document_id"])
        self.assertEqual("order-api-guide-v1.0", assertions["run_b_bge_rerank_leader_document_id"])
        self.assertEqual("order-api-release-v2.0", assertions["run_b_final_top_document_id"])
        self.assertEqual("preserved_final_top1", assertions["resolver_action"])


if __name__ == "__main__":
    unittest.main()
