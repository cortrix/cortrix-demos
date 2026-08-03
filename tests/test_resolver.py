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


class ResolverTests(unittest.TestCase):
    def test_resolver_rejects_superseded_top_result_and_selects_current(self) -> None:
        response = {
            "results": [
                {"child_id": "child-old", "score": 0.99, "content": "Use buyer_id."},
                {"child_id": "child-new", "score": 0.91, "content": "Use buyer_account_id."},
            ]
        }
        result = apply_lifecycle_resolver(response, FIXTURES, IDENTITY_MAP)
        self.assertTrue(result["pass"])
        self.assertEqual("new", result["decision"]["selected_document_id"])
        self.assertTrue(result["assertions"]["retrieval_top1_was_superseded"])
        self.assertTrue(result["assertions"]["resolver_changed_final_document"])

    def test_resolver_requires_durable_child_identity(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "durable child identity"):
            apply_lifecycle_resolver({"results": [{"child_id": "unknown"}]}, FIXTURES, IDENTITY_MAP)

    def test_resolver_rejects_a_story_where_the_current_document_is_already_top1(self) -> None:
        response = {
            "results": [
                {"child_id": "child-new", "score": 0.99, "content": "Use buyer_account_id."},
                {"child_id": "child-old", "score": 0.91, "content": "Use buyer_id."},
            ]
        }
        result = apply_lifecycle_resolver(response, FIXTURES, IDENTITY_MAP)
        self.assertFalse(result["pass"])
        self.assertFalse(result["assertions"]["retrieval_top1_was_superseded"])
        self.assertFalse(result["assertions"]["resolver_changed_final_document"])
        self.assertIn("already current", result["decision"]["reason"])


if __name__ == "__main__":
    unittest.main()
