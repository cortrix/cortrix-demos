from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.preflight import full_stack_preflight, verify_runtime


class PreflightTests(unittest.TestCase):
    SOURCE = {
        "release_commit": "e159974f936bd987d5718195d54cd70ff3acc2e5",
        "source_revision": "32b82f6f8f1d7a41349f408969ff03b7997b6c15",
    }

    def test_unreviewed_sixth_attempt_stops_before_secret_or_runtime_checks(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "must be 2, 3, 4, or 5"):
            full_stack_preflight(Path("missing-source"), Path("missing-price"), reviewed_attempt_limit=6, **self.SOURCE)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_stops_before_other_checks(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "no external call was made") as captured:
            full_stack_preflight(Path("missing-source"), Path("missing-price"), **self.SOURCE)
        error = captured.exception.as_dict()["error"]
        self.assertEqual("CX_DEMO_SECRET_MISSING", error["code"])
        self.assertEqual("auth", error["category"])
        self.assertFalse(error["retryable"])
        self.assertFalse(error["structured_data"]["external_calls_made"])
        self.assertIn("next_action", error["structured_data"])

    @patch("cortrix_demo_runner.preflight.subprocess.run")
    def test_unavailable_docker_engine_is_machine_retryable(self, run: object) -> None:
        run.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="engine unavailable")
        with self.assertRaises(DemoContractError) as captured:
            verify_runtime()
        error = captured.exception.as_dict()["error"]
        self.assertEqual("CX_DEMO_DOCKER_ENGINE_UNAVAILABLE", error["code"])
        self.assertEqual("transient", error["category"])
        self.assertTrue(error["retryable"])
        self.assertEqual(1000, error["retry_after_ms"])
        self.assertEqual("docker_engine", error["structured_data"]["requirement"])
        self.assertIn("next_action", error["structured_data"])

    @patch("cortrix_demo_runner.preflight.subprocess.run")
    def test_unavailable_compose_is_distinct_and_not_retryable(self, run: object) -> None:
        run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="29.5.3 29.5.3", stderr=""),
            subprocess.CompletedProcess([], 1, stdout="", stderr="compose unavailable"),
        ]
        with self.assertRaises(DemoContractError) as captured:
            verify_runtime()
        error = captured.exception.as_dict()["error"]
        self.assertEqual("CX_DEMO_COMPOSE_UNAVAILABLE", error["code"])
        self.assertEqual("permanent", error["category"])
        self.assertFalse(error["retryable"])
        self.assertNotIn("retry_after_ms", error)


if __name__ == "__main__":
    unittest.main()
