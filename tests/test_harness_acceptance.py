from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.harness_acceptance import _is_commit_ancestor, _usage_contract, _validate_safety, refresh_harness_checksums


ROOT = Path(__file__).resolve().parents[1]


class HarnessAcceptanceTests(unittest.TestCase):
    def test_curated_checksums_exclude_raw_harness_home(self) -> None:
        with TemporaryDirectory() as directory:
            run_dir = Path(directory) / "database-change-conflict-guardian-20260817T120000Z"
            (run_dir / "harness-home" / "sessions").mkdir(parents=True)
            (run_dir / "run-a").mkdir(parents=True)
            (run_dir / "run-a" / "summary.json").write_text("{}\n", encoding="utf-8")
            (run_dir / "harness-home" / "sessions" / "session.jsonl").write_text("private runtime session\n", encoding="utf-8")
            result = refresh_harness_checksums(run_dir)
            self.assertEqual(["run-a/summary.json"], [item["path"] for item in result["files"]])

    def test_public_safety_ignores_raw_harness_dependencies_but_rejects_curated_symlinks(self) -> None:
        with TemporaryDirectory() as directory:
            run_dir = Path(directory) / "database-change-conflict-guardian-20260817T120000Z"
            raw_dependencies = run_dir / "harness-home" / "profiles" / "node_modules"
            raw_dependencies.mkdir(parents=True)
            (raw_dependencies / "dependency").symlink_to("../package")
            _validate_safety(run_dir)
            result = refresh_harness_checksums(run_dir)
            self.assertEqual([], result["files"])

            (run_dir / "run-a").mkdir(parents=True)
            (run_dir / "run-a" / "summary.json").symlink_to("../summary.json")
            with self.assertRaisesRegex(DemoContractError, "contains a symbolic link"):
                _validate_safety(run_dir)

    def test_harness_schema_has_independent_acceptance_and_screenshot_gates(self) -> None:
        schema = json.loads((ROOT / "packages" / "evidence-schema" / "harness-run-manifest.schema.json").read_text(encoding="utf-8"))
        self.assertIn("acceptance", schema["properties"])
        self.assertIn("post_screenshot_human_review_required", schema["properties"])
        self.assertEqual("independent_clean_room", schema["properties"]["acceptance"]["properties"]["method"]["const"])
        self.assertEqual(2, len(schema["allOf"]))
        self.assertEqual([0.3, 0.6, 1.0, 5.0], schema["properties"]["usage"]["properties"]["budget_usd"]["enum"])

    def test_usage_contract_accepts_current_campaign_and_frozen_archive_budgets(self) -> None:
        foundation_current, foundation_calls = _usage_contract(ROOT / "scenarios" / "database-change-conflict-guardian", include_historical=False)
        continuity_current, continuity_calls = _usage_contract(ROOT / "scenarios" / "payment-incident-shift-handoff", include_historical=False)
        foundation_historical, _ = _usage_contract(ROOT / "scenarios" / "database-change-conflict-guardian", include_historical=True)
        continuity_historical, _ = _usage_contract(ROOT / "scenarios" / "payment-incident-shift-handoff", include_historical=True)
        self.assertEqual({0.3}, foundation_current)
        self.assertEqual({0.6}, continuity_current)
        self.assertEqual({0.3, 1.0}, foundation_historical)
        self.assertEqual({0.6, 5.0}, continuity_historical)
        self.assertEqual(5, foundation_calls)
        self.assertEqual(9, continuity_calls)

    def test_clean_room_tooling_may_descend_from_the_candidate_commit(self) -> None:
        with TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-b", "main"], cwd=repository, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Cortrix Test"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repository, check=True)
            tracked = repository / "tracked.txt"
            tracked.write_text("candidate\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-m", "candidate"], cwd=repository, check=True, capture_output=True)
            candidate = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
            tracked.write_text("tooling\n", encoding="utf-8")
            subprocess.run(["git", "commit", "-am", "tooling"], cwd=repository, check=True, capture_output=True)
            tooling = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()

            self.assertTrue(_is_commit_ancestor(repository, candidate, tooling))
            self.assertFalse(_is_commit_ancestor(repository, tooling, candidate))


if __name__ == "__main__":
    unittest.main()
