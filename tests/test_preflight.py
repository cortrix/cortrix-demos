from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.preflight import full_stack_preflight


class PreflightTests(unittest.TestCase):
    def test_unreviewed_sixth_attempt_stops_before_secret_or_runtime_checks(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "must be 2, 3, 4, or 5"):
            full_stack_preflight(Path("missing-source"), Path("missing-price"), reviewed_attempt_limit=6)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_stops_before_other_checks(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "no external call was made"):
            full_stack_preflight(Path("missing-source"), Path("missing-price"))


if __name__ == "__main__":
    unittest.main()
