"""Keep component progress separate from finished work in the presentation."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cortrix_live_demo.event_projection import details


class ProjectionTests(unittest.TestCase):
    def test_controller_clock_identifiers_preserve_nanosecond_precision(self):
        raw = {"source": "controller", "started_monotonic_ns": 10000000000000001, "ended_monotonic_ns": 10000000001000001}
        projected = details("ingest_completed", raw)
        self.assertEqual(projected["started_monotonic_ns"], "10000000000000001")
        self.assertEqual(projected["ended_monotonic_ns"], "10000000001000001")
        self.assertEqual(raw["started_monotonic_ns"], 10000000000000001)
        self.assertNotIn("started_monotonic_ns", details("provider_request", {"source": "deepseek", "started_monotonic_ns": 1}))

    def test_processing_receipt_is_not_presented_as_completed(self):
        self.assertEqual(details("document_task_progress", {"response": {"status": "processing"}})["state"], "processing")
        self.assertEqual(details("document_task_progress", {"response": {"status": "completed", "error_code": "failure"}})["state"], "failed")

    def test_counts_come_only_from_recorded_native_objects(self):
        result = details("document_written", {"document_id": "doc", "after": {"documents": [{"deleted_at": None}], "text_blocks": [{}, {}]}})
        self.assertEqual(result["document_count"], 1)
        self.assertEqual(result["chunk_count"], 2)
        self.assertNotIn("document_count", details("provider_request", {}))

    def test_vector_export_owner_is_projected_without_mutating_receipt(self):
        original = {"source": "business_step", "step_id": "vectors_export", "owner": "cortrix"}
        projected = details("business_step_completed", original)
        self.assertEqual(projected["owner"], "application")
        self.assertEqual(projected["recorded_owner"], "cortrix")
        self.assertEqual(original["owner"], "cortrix")
