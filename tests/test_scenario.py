from __future__ import annotations

from pathlib import Path
import unittest

from cortrix_demo_runner.scenario import load_scenario, validate_scenario


ROOT = Path(__file__).resolve().parents[1]


class ScenarioTests(unittest.TestCase):
    def test_scenario_identity_and_fixture_checksums(self) -> None:
        self.assertEqual([], validate_scenario(ROOT))

    def test_source_identity_is_separate_from_release_identity(self) -> None:
        requires = load_scenario(ROOT)["requires"]
        self.assertEqual("v1.0.0-rc.1", requires["cortrix_release"])
        self.assertNotEqual(requires["cortrix_release_commit"], requires["cortrix_source_revision"])


if __name__ == "__main__":
    unittest.main()
