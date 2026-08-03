from __future__ import annotations

import unittest

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.resolver import apply_lifecycle_resolver


FIXTURES = {
    "documents": [
        {"document_id": "old", "version": "v1", "status": "superseded", "source": "guide"},
        {"document_id": "new", "version": "v2", "status": "current", "source": "release"},
    ],
    "resolver": {
        "owner": "demo_application_policy",
        "rule": "select current",
        "expected_document_id": "new",
        "expected_field": "buyer_account_id",
    },
}
IDENTITY_MAP = {
    "child-old": {"document_id": "old", "doc_id": "doc-old"},
    "child-new": {"document_id": "new", "doc_id": "doc-new"},
}
FROZEN = {
    "run_b_required_document_ids": ["old", "new"],
    "run_b_final_top_document_id": "new",
    "run_b_final_top_document_status": "current",
    "resolver_selected_document_id": "new",
    "resolver_selected_field": "buyer_account_id",
    "resolver_action": "preserved_final_top1",
}


class ResolverTests(unittest.TestCase):
    def test_layered_contract_accepts_observed_bge_leader_and_current_final_top1(self) -> None:
        response = {
            "results": [
                {"child_id": "child-new", "score": 0.67, "rerank_score": 0.63, "content": "Use buyer_account_id."},
                {"child_id": "child-old", "score": 0.33, "rerank_score": 0.75, "content": "Use account_id."},
            ]
        }
        result = apply_lifecycle_resolver(response, FIXTURES, IDENTITY_MAP, FROZEN)
        self.assertTrue(result["pass"])
        self.assertEqual("new", result["decision"]["selected_document_id"])
        self.assertEqual("old", result["layers"]["bge_cross_encoder"]["leader"]["document_id"])
        self.assertEqual("new", result["layers"]["deepseek_listwise_final"]["top_result"]["document_id"])
        self.assertEqual("preserved_final_top1", result["layers"]["application_lifecycle_policy"]["action"])
        self.assertTrue(result["assertions"]["required_documents_retrieved"])
        self.assertTrue(result["assertions"]["bge_scores_present"])
        self.assertTrue(result["assertions"]["final_top1_matches_contract"])
        self.assertTrue(result["assertions"]["policy_action_matches_contract"])

    def test_resolver_requires_durable_child_identity(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "durable child identity"):
            apply_lifecycle_resolver({"results": [{"child_id": "unknown"}]}, FIXTURES, IDENTITY_MAP, FROZEN)

    def test_layered_contract_rejects_superseded_final_top1(self) -> None:
        response = {
            "results": [
                {"child_id": "child-old", "score": 0.67, "rerank_score": 0.75, "content": "Use account_id."},
                {"child_id": "child-new", "score": 0.33, "rerank_score": 0.63, "content": "Use buyer_account_id."},
            ]
        }
        result = apply_lifecycle_resolver(response, FIXTURES, IDENTITY_MAP, FROZEN)
        self.assertFalse(result["pass"])
        self.assertFalse(result["assertions"]["final_top1_matches_contract"])
        self.assertFalse(result["assertions"]["policy_action_matches_contract"])
        self.assertIn("changes the final top result", result["decision"]["reason"])

    def test_layered_contract_accepts_a_current_bge_leader(self) -> None:
        response = {
            "results": [
                {"child_id": "child-new", "score": 0.67, "rerank_score": 0.80, "content": "Use buyer_account_id."},
                {"child_id": "child-old", "score": 0.33, "rerank_score": 0.75, "content": "Use account_id."},
            ]
        }
        result = apply_lifecycle_resolver(response, FIXTURES, IDENTITY_MAP, FROZEN)
        self.assertTrue(result["pass"])
        self.assertEqual("new", result["layers"]["bge_cross_encoder"]["leader"]["document_id"])

    def test_layered_contract_rejects_a_missing_version_conflict_document(self) -> None:
        response = {
            "results": [
                {"child_id": "child-new", "score": 0.67, "rerank_score": 0.80, "content": "Use buyer_account_id."},
                {"child_id": "child-new", "score": 0.33, "rerank_score": 0.75, "content": "Use buyer_account_id."},
            ]
        }
        result = apply_lifecycle_resolver(response, FIXTURES, IDENTITY_MAP, FROZEN)
        self.assertFalse(result["pass"])
        self.assertFalse(result["assertions"]["required_documents_retrieved"])

    def test_layered_contract_requires_finite_bge_scores(self) -> None:
        response = {
            "results": [
                {"child_id": "child-new", "rerank_score": 0.63, "content": "Use buyer_account_id."},
                {"child_id": "child-old", "content": "Use account_id."},
            ]
        }
        with self.assertRaisesRegex(DemoContractError, "finite BGE rerank score"):
            apply_lifecycle_resolver(response, FIXTURES, IDENTITY_MAP, FROZEN)

    def test_layered_contract_rejects_fixture_and_assertion_drift(self) -> None:
        drifted = {**FROZEN, "resolver_selected_document_id": "old"}
        response = {
            "results": [
                {"child_id": "child-new", "rerank_score": 0.63, "content": "Use buyer_account_id."},
                {"child_id": "child-old", "rerank_score": 0.75, "content": "Use account_id."},
            ]
        }
        with self.assertRaisesRegex(DemoContractError, "do not match"):
            apply_lifecycle_resolver(response, FIXTURES, IDENTITY_MAP, drifted)


if __name__ == "__main__":
    unittest.main()
