from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.preflight import full_stack_preflight


class PreflightTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_stops_before_other_checks(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "no external call was made"):
            full_stack_preflight(Path("missing-source"), Path("missing-price"))


if __name__ == "__main__":
    unittest.main()
