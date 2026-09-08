"""Reject ambiguous, unsupported, and stale evidence during answer extraction."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cortrix_live_demo.answer_normalization import normalize_answer


class NormalizationTests(unittest.TestCase):
    def test_explanation_can_be_preserved_while_one_json_decision_is_verified(self):
        decision = {"selected_field": "current_key", "document_id": "current-doc", "evidence_ref": "run:pg:1:current-doc"}
        query = {"ranking": [{"rank": 1, "document_id": "current-doc", "lifecycle_status": "current", "content": "Use current_key."}], "resolver": {"selected_field": "current_key", "selected_document_id": "current-doc"}}
        result = normalize_answer("An explanation.\n" + json.dumps(decision), "run", "pg", query)
        self.assertTrue(result["verified"])
        self.assertTrue(result["normalization_applied"])
        self.assertFalse(result["original_strict_json"])

    def test_duplicate_json_or_wrong_reference_does_not_become_an_answer(self):
        decision = {"selected_field": "current_key", "document_id": "current-doc", "evidence_ref": "run:pg:1:current-doc"}
        query = {"ranking": [], "resolver": {"selected_field": "current_key", "selected_document_id": "current-doc"}}
        self.assertFalse(normalize_answer(json.dumps(decision), "run", "pg", query)["verified"])
        self.assertFalse(normalize_answer(json.dumps(decision) + json.dumps(decision), "run", "pg", query)["verified"])

    def test_hidden_rank_truncated_content_and_invalid_fields_are_rejected(self):
        decision = {"selected_field": "current_key", "document_id": "current-doc", "evidence_ref": "run:pg:9:current-doc"}
        query = {"ranking": [{"rank": rank, "document_id": "current-doc", "lifecycle_status": "current", "content": "Use current_key."} for rank in range(1, 10)], "resolver": {"selected_field": "current_key", "selected_document_id": "current-doc"}}
        self.assertFalse(normalize_answer(json.dumps(decision), "run", "pg", query)["verified"])
        decision["evidence_ref"] = "run:pg:1:current-doc"
        query["ranking"][0]["content"] = "x" * 2048 + "current_key"
        self.assertFalse(normalize_answer(json.dumps(decision), "run", "pg", query)["verified"])
        decision["selected_field"] = []
        self.assertFalse(normalize_answer(json.dumps(decision), "run", "pg", query)["verified"])
