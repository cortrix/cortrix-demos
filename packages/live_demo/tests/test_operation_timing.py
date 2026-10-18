"""Tests for durable operation and business-step timing receipts."""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


from cortrix_live_demo import operation_timing


class Paused(RuntimeError):
    pass


class CancelledError(RuntimeError):
    pass


class OperationTimingTests(unittest.TestCase):
    def test_success_has_one_closed_terminal_receipt(self):
        events = []
        with patch.object(operation_timing.time, "monotonic_ns", side_effect=[100, 250]):
            with operation_timing.timed_attempt(lambda stage, value: events.append((stage, value)), "pg_search", "query", "postgresql") as attempt:
                self.assertEqual(attempt["started_monotonic_ns"], 100)
        self.assertEqual([stage for stage, _ in events], ["business_step_started", "business_step_completed"])
        started, completed = events[0][1], events[1][1]
        self.assertEqual(started["state"], "started")
        self.assertEqual(started["status"], started["state"])
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(completed["status"], completed["state"])
        self.assertEqual(completed["attempt_id"], started["attempt_id"])
        self.assertEqual(completed["duration_ns"], 150)
        self.assertEqual(completed["duration_ms"], 0.00015)
        self.assertEqual(completed["schema_version"], 2)
        self.assertEqual(completed["timing_scope"], "step")
        self.assertEqual(completed["process_instance_id"], operation_timing.process_instance_id)

    def test_failure_is_recorded_once_and_reraised(self):
        events = []
        with self.assertRaisesRegex(ValueError, "broken"):
            with operation_timing.timed_attempt(lambda stage, value: events.append((stage, value)), "documents_ingest", "ingest", "cortrix"):
                raise ValueError("broken")
        self.assertEqual([stage for stage, _ in events], ["business_step_started", "business_step_failed"])
        self.assertEqual(events[-1][1]["status"], "failed")
        self.assertEqual(events[-1][1]["state"], "failed")
        self.assertEqual(events[-1][1]["error_type"], "ValueError")

    def test_command_exception_does_not_record_its_runtime_path(self):
        events = []
        command_path = str(Path.cwd() / "operator-only" / "launch.mjs")
        with self.assertRaises(subprocess.TimeoutExpired):
            with operation_timing.timed_attempt(lambda stage, value: events.append((stage, value)), "harness", "agent", "application"):
                raise subprocess.TimeoutExpired(["node", command_path], 5)
        self.assertNotIn(command_path, events[-1][1]["error"])
        self.assertEqual("Operation failed; inspect private operator logs.", events[-1][1]["error"])

    def test_cancel_and_pause_use_distinct_terminal_states(self):
        cases = [
            (Paused("DEMO_CANCELLED"), "business_step_cancelled", "cancelled"),
            (RuntimeError("cancelled by operator"), "business_step_cancelled", "cancelled"),
            (CancelledError(), "business_step_cancelled", "cancelled"),
            (Paused("DEMO_BUDGET_PAUSED"), "business_step_paused", "paused"),
        ]
        for error, terminal_stage, status in cases:
            with self.subTest(status=status, message=str(error)):
                events = []
                with self.assertRaises(type(error)):
                    with operation_timing.timed_attempt(lambda stage, value: events.append((stage, value)), "enrichment_wait", "ingest", "cortrix"):
                        raise error
                self.assertEqual([stage for stage, _ in events], ["business_step_started", terminal_stage])
                self.assertEqual(events[-1][1]["status"], status)
                self.assertEqual(events[-1][1]["state"], status)
                self.assertIn("ended_monotonic_ns", events[-1][1])

    def test_nested_attempt_links_parent_without_summing_durations(self):
        events = []
        with patch.object(operation_timing.time, "monotonic_ns", side_effect=[10, 20, 30, 40]):
            with operation_timing.timed_attempt(lambda stage, value: events.append((stage, value)), "evidence_verify", "query", "application") as outer:
                with operation_timing.timed_attempt(lambda stage, value: events.append((stage, value)), "business_resolve", "query", "application") as inner:
                    self.assertEqual(inner["parent_attempt_id"], outer["attempt_id"])
        terminals = {value["step_id"]: value for stage, value in events if stage == "business_step_completed"}
        self.assertEqual(terminals["business_resolve"]["duration_ns"], 10)
        self.assertEqual(terminals["evidence_verify"]["duration_ns"], 30)
        self.assertIsNone(outer["parent_attempt_id"])

    def test_custom_controller_event_contract_is_preserved(self):
        events = []
        with operation_timing.timed_attempt(
            lambda stage, value: events.append((stage, value)),
            "query",
            "query",
            "application",
            source="controller",
            event_prefix="query",
            timing_scope="operation",
        ):
            pass
        self.assertEqual([stage for stage, _ in events], ["query_started", "query_completed"])
        self.assertEqual(events[-1][1]["source"], "controller")
        self.assertEqual(events[-1][1]["timing_scope"], "operation")
        self.assertEqual(events[-1][1]["state"], "completed")

    def test_current_context_exposes_only_receipt_linkage(self):
        self.assertEqual(operation_timing.current_timing_context(), {
            "parent_attempt_id": None,
            "process_instance_id": operation_timing.process_instance_id,
        })
        with operation_timing.timed_attempt(lambda stage, value: None, "pg_search", "query", "postgresql") as attempt:
            context = operation_timing.current_timing_context()
            self.assertEqual(context, {
                "parent_attempt_id": attempt["attempt_id"],
                "process_instance_id": operation_timing.process_instance_id,
            })
        self.assertIsNone(operation_timing.current_timing_context()["parent_attempt_id"])


if __name__ == "__main__":
    unittest.main()
