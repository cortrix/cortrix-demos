"""Keep final JSON, policy, and visible evidence checks independent and strict."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cortrix_live_demo.answer_contract import validate_answer


class AnswerContractTests(unittest.TestCase):
    def setUp(self):
        self.decision = {"selected_field": "current_key", "document_id": "current-doc", "evidence_ref": "run:pg:1:current-doc"}
        self.policy = {"selected_field": "current_key", "selected_document_id": "current-doc"}
        self.projection = {"operation": "query", "status": "ok", "evidence": [
            {"evidence_ref": "run:pg:1:current-doc", "document_id": "current-doc", "lifecycle_status": "current", "content": "Send `current_key` in the request."}]}

    def check_answer(self, value=None, raw=None):
        return validate_answer(json.dumps(value or self.decision) if raw is None else raw, self.projection, self.policy)

    def test_exact_original_answer_passes_without_normalization(self):
        result = self.check_answer()
        self.assertEqual(result["business_verdict"], "pass")
        self.assertFalse(result["normalization_applied"])
        self.assertEqual(len(result["raw_answer_sha256"]), 64)
        self.assertTrue(all(result["assertions"].values()))

    def test_explanation_fence_empty_and_duplicate_objects_fail(self):
        raw = json.dumps(self.decision)
        for candidate in ("Explanation.\n" + raw, "```json\n" + raw + "\n```", "", raw + raw):
            with self.subTest(candidate=candidate):
                result = self.check_answer(raw=candidate)
                self.assertEqual(result["business_verdict"], "fail")
                self.assertFalse(result["assertions"]["decision_is_object"])

    def test_duplicate_keys_and_extra_keys_are_rejected(self):
        raw = json.dumps(self.decision)[:-1] + ', "selected_field": "current_key"}'
        self.assertEqual(self.check_answer(raw=raw)["failure_codes"], ["invalid_json_or_duplicate_keys"])
        extra = {**self.decision, "explanation": "Correct"}
        self.assertEqual(self.check_answer(value=extra)["failure_codes"], ["unexpected_decision_keys"])

    def test_field_types_and_explicit_abstention_are_distinct(self):
        for value in ([], 1, True, None, "", "   "):
            self.assertEqual(self.check_answer(value={**self.decision, "selected_field": value})["business_verdict"], "fail")
        result = self.check_answer(value={key: None for key in self.decision})
        self.assertTrue(result["abstained"])
        self.assertEqual(result["failure_codes"], ["explicit_abstention"])

    def test_wrong_cross_path_or_missing_reference_fails(self):
        for reference in ("other:pg:1:current-doc", "run:b:1:current-doc", "missing"):
            result = self.check_answer(value={**self.decision, "evidence_ref": reference})
            self.assertFalse(result["assertions"]["citation_matches_returned_current_document"])
            self.assertEqual(result["business_verdict"], "fail")

    def test_stale_duplicate_and_unsupported_visible_evidence_fail(self):
        self.projection["evidence"][0]["lifecycle_status"] = "superseded"
        self.assertEqual(self.check_answer()["business_verdict"], "fail")
        self.projection["evidence"][0]["lifecycle_status"] = "current"
        self.projection["evidence"].append(copy.deepcopy(self.projection["evidence"][0]))
        self.assertEqual(self.check_answer()["business_verdict"], "fail")
        self.projection["evidence"].pop()
        self.projection["evidence"][0]["content"] = "Only buyer_current_key is documented."
        self.assertFalse(self.check_answer()["assertions"]["field_present_in_visible_evidence"])

    def test_policy_and_successful_query_are_required(self):
        self.policy["selected_field"] = "unknown"
        self.assertEqual(self.check_answer()["business_verdict"], "fail")
        self.policy["selected_field"] = "current_key"
        self.projection["status"] = "partial"
        self.assertEqual(self.check_answer()["failure_codes"], ["successful_query_receipt_required"])


if __name__ == "__main__":
    unittest.main()
