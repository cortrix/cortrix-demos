from __future__ import annotations

import ast
from pathlib import Path
import unittest

from cortrix_demo_runner.acceptance import png_dimensions_from_header, require_object
from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.live import failure_category
from cortrix_demo_runner.runtime import _http_status_error, _timeout_error
from cortrix_demo_runner.walkthrough import record_pricing_snapshot, require_phase


ROOT = Path(__file__).resolve().parents[1]
EXECUTION_MODULES = ("live.py", "walkthrough.py", "acceptance.py")


class ExecutionErrorContractTests(unittest.TestCase):
    def test_execution_modules_never_construct_the_generic_error_code(self) -> None:
        source_root = ROOT / "packages" / "runner" / "src" / "cortrix_demo_runner"
        for filename in EXECUTION_MODULES:
            tree = ast.parse((source_root / filename).read_text(encoding="utf-8"), filename=filename)
            calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "DemoContractError"
            ]
            self.assertTrue(calls, filename)
            for call in calls:
                code = next((keyword.value for keyword in call.keywords if keyword.arg == "code"), None)
                self.assertIsInstance(code, ast.Constant, f"{filename}:{call.lineno} must set an explicit code")
                self.assertNotEqual("CX_DEMO_CONTRACT_VIOLATION", code.value, f"{filename}:{call.lineno}")

    def test_terminal_acceptance_error_has_no_repair_action(self) -> None:
        with self.assertRaises(DemoContractError) as captured:
            require_object([], "Candidate manifest")
        error = captured.exception.as_dict()["error"]
        self.assertEqual("CX_DEMO_ACCEPTANCE_INTEGRITY_VIOLATION", error["code"])
        self.assertFalse(error["retryable"])
        self.assertNotIn("next_action", error["structured_data"])

    def test_screenshot_input_error_is_safe_to_correct(self) -> None:
        with self.assertRaises(DemoContractError) as captured:
            png_dimensions_from_header(b"not-a-png")
        error = captured.exception.as_dict()["error"]
        self.assertEqual("CX_DEMO_SCREENSHOT_INPUT_INVALID", error["code"])
        self.assertIn("next_action", error["structured_data"])

    def test_walkthrough_input_and_phase_errors_are_actionable(self) -> None:
        with self.assertRaises(DemoContractError) as pricing:
            record_pricing_snapshot(ROOT, Path("unused.json"), -1, 0, 0)
        self.assertEqual("CX_DEMO_WALKTHROUGH_INPUT_INVALID", pricing.exception.code)
        self.assertIn("next_action", pricing.exception.structured_data)

        with self.assertRaises(DemoContractError) as phase:
            require_phase({"phase": "initialized"}, "run_a_complete")
        self.assertEqual("CX_DEMO_WALKTHROUGH_PHASE_INVALID", phase.exception.code)
        self.assertEqual("initialized", phase.exception.structured_data["current_phase"])
        self.assertIn("next_action", phase.exception.structured_data)

    def test_http_and_timeout_errors_drive_retry_without_message_parsing(self) -> None:
        rate_limit = _http_status_error("POST /query", 429)
        server_error = _http_status_error("POST /query", 503)
        timeout = _timeout_error("POST /query", 30)
        client_error = _http_status_error("POST /query", 422)

        self.assertEqual("http_429", failure_category(rate_limit))
        self.assertEqual("http_5xx", failure_category(server_error))
        self.assertEqual("timeout", failure_category(timeout))
        self.assertEqual("deterministic_or_contract_failure", failure_category(client_error))
        for error in (rate_limit, server_error, timeout):
            self.assertTrue(error.retryable)
            self.assertIsInstance(error.retry_after_ms, int)
        self.assertFalse(client_error.retryable)


if __name__ == "__main__":
    unittest.main()
