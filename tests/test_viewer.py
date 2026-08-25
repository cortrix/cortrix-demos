from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
import json

from packages.viewer.serve import CandidateQAError, HarnessViewerError, LOOPBACK, create_candidate_qa_config, create_harness_config, create_server


ROOT = Path(__file__).resolve().parents[1]


class ViewerServerTests(unittest.TestCase):
    @patch("packages.viewer.serve.ThreadingHTTPServer")
    def test_unavailable_preferred_address_falls_back_to_loopback(self, server_type: MagicMock) -> None:
        fallback_server = MagicMock()
        server_type.side_effect = [OSError("address unavailable"), fallback_server]
        server, bind, used_fallback = create_server("192.0.2.1", 18765)
        self.assertIs(fallback_server, server)
        self.assertEqual(LOOPBACK, bind)
        self.assertTrue(used_fallback)
        self.assertEqual((LOOPBACK, 18765), server_type.call_args_list[1].args[0])

    @patch("packages.viewer.serve.ThreadingHTTPServer")
    def test_loopback_failure_is_not_hidden(self, server_type: MagicMock) -> None:
        server_type.side_effect = OSError("port unavailable")
        with self.assertRaises(OSError):
            create_server(LOOPBACK, 18765)
        self.assertEqual(1, server_type.call_count)

    def write_candidate(self, root: Path, *, state: str = "candidate", acceptance: object = None) -> str:
        run_id = "order-api-field-migration-20260810T094554Z"
        viewer = root / "packages" / "viewer"
        scenario = root / "scenarios" / "order-api-field-migration"
        run_dir = root / ".runs" / run_id
        (scenario / "web").mkdir(parents=True)
        (scenario / "profiles").mkdir(parents=True)
        (run_dir / "run-a").mkdir(parents=True)
        (run_dir / "run-b").mkdir(parents=True)
        viewer.mkdir(parents=True)
        (scenario / "web" / "scenario.json").write_text("{}", encoding="utf-8")
        (scenario / "profiles" / "technology-profile.json").write_text("{}", encoding="utf-8")
        (run_dir / "run-a" / "pgvector-result.json").write_text("{}", encoding="utf-8")
        (run_dir / "run-b" / "resolver-01.json").write_text("{}", encoding="utf-8")
        (viewer / "viewer-config.json").write_text(
            json.dumps(
                {
                    "scenario": "order-api-field-migration",
                    "scenario_metadata": "../../scenarios/order-api-field-migration/web/scenario.json",
                    "technology_profile": "../../scenarios/order-api-field-migration/profiles/technology-profile.json",
                    "accepted_pointer": "../../scenarios/order-api-field-migration/evidence/accepted-run.json",
                }
            ),
            encoding="utf-8",
        )
        manifest = {
            "run_id": run_id,
            "state": state,
            "screenshot_eligible": False,
            "human_review_required": True,
            "run_a": {"path": "run-a/pgvector-result.json"},
            "resolver": {"path": "run-b/resolver-01.json"},
        }
        if acceptance is not None:
            manifest["acceptance"] = acceptance
        (run_dir / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return run_id

    def test_candidate_qa_config_is_scoped_to_one_unaccepted_run(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = self.write_candidate(root)
            config = create_candidate_qa_config(root, run_id)
        self.assertEqual("candidate_qa", config["mode"])
        self.assertEqual(run_id, config["candidate"]["run_id"])
        self.assertEqual(f"/.runs/{run_id}/run-manifest.json", config["candidate"]["manifest"])

    def test_candidate_qa_refuses_accepted_or_promoted_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = self.write_candidate(root, state="accepted")
            with self.assertRaisesRegex(CandidateQAError, "identity or state"):
                create_candidate_qa_config(root, run_id)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = self.write_candidate(root, acceptance={"verdict": "pass"})
            with self.assertRaisesRegex(CandidateQAError, "acceptance metadata"):
                create_candidate_qa_config(root, run_id)

    def test_candidate_qa_refuses_evidence_path_traversal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = self.write_candidate(root)
            manifest_path = root / ".runs" / run_id / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["run_a"]["path"] = "../../outside.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(CandidateQAError, "escapes its run directory"):
                create_candidate_qa_config(root, run_id)

    def test_harness_viewer_refuses_an_unaccepted_pointer(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pointer = root / "scenarios" / "database-change-conflict-guardian" / "evidence" / "accepted-run.json"
            pointer.parent.mkdir(parents=True)
            pointer.write_text(json.dumps({"status": "not_yet_accepted", "run_id": None}), encoding="utf-8")
            with self.assertRaisesRegex(HarnessViewerError, "does not have an accepted run"):
                create_harness_config(root, "database-change-conflict-guardian")

    def test_harness_viewer_exposes_the_accepted_foundation_scenarios(self) -> None:
        for scenario in ("database-change-conflict-guardian", "api-version-drift-coding-agent"):
            with self.subTest(scenario=scenario):
                config = create_harness_config(ROOT, scenario)
                self.assertEqual("accepted_harness", config["mode"])
                self.assertEqual(scenario, config["scenario_id"])
                self.assertIn(f"/scenarios/{scenario}/evidence/runs/", config["manifest"])

    def test_harness_browser_identity_uses_run_ids_for_summaries_and_scenario_ids_for_resolvers(self) -> None:
        source = (ROOT / "packages" / "viewer" / "harness.js").read_text(encoding="utf-8")
        self.assertIn("const sameRun = [runA, runB, review]", source)
        self.assertIn("const sameScenario = [resolverA, resolverB]", source)
        html = (ROOT / "packages" / "viewer" / "harness.html").read_text(encoding="utf-8")
        self.assertIn('src="./harness.js?v=3"', html)


if __name__ == "__main__":
    unittest.main()
