from __future__ import annotations

import struct
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zlib

from cortrix_demo_runner.acceptance import REQUIRED_PATH_NAMES, png_dimensions, png_dimensions_from_header, record_screenshot, stage_accepted, validate_manifest_contract, validate_run_id, verify_accepted
from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.fresh_clone import verify_readme
from cortrix_demo_runner.io import sha256_file, write_json
from cortrix_demo_runner.scenario import RELEASE, RELEASE_COMMIT, SCENARIO_ID, SOURCE_REVISION


class AcceptanceContractTests(unittest.TestCase):
    def png_bytes(self, width: int = 800, height: int = 450) -> bytes:
        def chunk(name: bytes, value: bytes) -> bytes:
            return struct.pack(">I", len(value)) + name + value + struct.pack(">I", zlib.crc32(name + value) & 0xFFFFFFFF)

        header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        rows = b"".join(b"\x00" + b"\xff\xff\xff\xff" * width for _ in range(height))
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")

    def accepted_contract_manifest(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "scenario_id": SCENARIO_ID,
            "assertions": {name: True for name in ("run_a", "run_b", "required_paths", "resolver", "cleanup", "budget", "model_checksums", "all_passed")},
            "required_paths": {name: True for name in REQUIRED_PATH_NAMES},
            "target_identity": {"release": RELEASE, "release_commit": RELEASE_COMMIT, "source_revision": SOURCE_REVISION, "container_digest": "sha256:" + "1" * 64, "demo_commit": "a" * 40},
            "fixture_manifest_sha256": "2" * 64,
            "provider_identity": {"provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/v1", "local_generative_llm": False},
            "cleanup": {"namespaces_removed": True, "containers_removed": True, "ports_released": True, "runtime_secret_removed": True},
            "cost": {"budget_usd": 1.0, "within_budget_contract": True, "public_cost_claim_allowed": False, "usage_visibility": "partial", "model": "deepseek-v4-flash", "observable_input_tokens": 1, "observable_output_tokens": 1, "observable_call_count_minimum": 5, "pricing_snapshot": {"official_url": "https://api-docs.deepseek.com/quick_start/pricing", "observed_at": "2026-08-03T12:00:00Z", "model": "deepseek-v4-flash", "currency": "USD"}},
            "run_a": {"path": "run-a/pgvector-result.json", "pass": True},
            "run_b": {"path": "run-b/summary.json", "pass": True, "serial_query_count": 2},
            "resolver": {"path": "run-b/resolver-01.json", "pass": True},
            "disclosed_gaps": [{"id": "partial-usage", "note": "Only observable usage is recorded."}],
            "claim_boundary": "Runtime evidence for this scenario only.",
        }

    def layered_resolver(self, run_id: str) -> dict[str, object]:
        return {
            "schema_version": 2,
            "run_id": run_id,
            "pass": True,
            "assertions": {
                name: True
                for name in (
                    "selected_expected_document",
                    "selected_content_contains_expected_field",
                    "bge_rerank_leader_was_superseded",
                    "bge_rerank_leader_was_strict",
                    "final_top1_is_current",
                    "policy_preserved_final_top1",
                )
            },
            "layers": {
                "bge_cross_encoder": {"leader": {"document_id": "order-api-guide-v1.0", "lifecycle_status": "superseded"}},
                "deepseek_listwise_final": {"top_result": {"document_id": "order-api-release-v2.0", "lifecycle_status": "current"}},
                "application_lifecycle_policy": {"action": "preserved_final_top1"},
            },
            "decision": {"selected_document_id": "order-api-release-v2.0", "selected_field": "buyer_account_id"},
        }

    def test_frozen_run_id_accepts_initial_and_retry_attempts(self) -> None:
        validate_run_id("order-api-field-migration-20260803T120000Z")
        validate_run_id("order-api-field-migration-20260803T120000Z-retry")

    def test_run_id_rejects_path_or_scenario_changes(self) -> None:
        for value in ("../run", "other-scenario-20260803T120000Z", "order-api-field-migration-latest"):
            with self.subTest(value=value), self.assertRaises(DemoContractError):
                validate_run_id(value)

    def test_png_contract_reads_ihdr_dimensions(self) -> None:
        header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1600, 900)
        self.assertEqual((1600, 900), png_dimensions_from_header(header))

    def test_png_contract_rejects_small_or_non_png_images(self) -> None:
        small = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 799, 449)
        with self.assertRaises(DemoContractError):
            png_dimensions_from_header(small)
        with self.assertRaises(DemoContractError):
            png_dimensions_from_header(b"not-a-png")

    def test_png_file_contract_requires_complete_crc_checked_image_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "viewer.png"
            path.write_bytes(self.png_bytes())
            self.assertEqual((800, 450), png_dimensions(path))
            value = bytearray(path.read_bytes())
            value[-1] ^= 1
            path.write_bytes(value)
            with self.assertRaises(DemoContractError):
                png_dimensions(path)

    def test_readme_exposes_result_run_and_evidence_in_order(self) -> None:
        verify_readme("# Demo\n\n## See the result\nA\n## Run it locally\nB\n## Inspect the evidence\nC\n")

    def test_readme_rejects_missing_or_reordered_first_run_sections(self) -> None:
        with self.assertRaises(DemoContractError):
            verify_readme("## Run it locally\n## See the result\n## Inspect the evidence\n")

    def test_viewer_consumes_the_run_manifest_schema_fields(self) -> None:
        root = Path(__file__).resolve().parents[1]
        viewer = (root / "packages" / "viewer" / "app.js").read_text(encoding="utf-8")
        self.assertIn('manifest.state !== "accepted"', viewer)
        self.assertIn("manifest.target_identity?.source_revision", viewer)
        self.assertIn("manifest.provider_identity?.model", viewer)
        self.assertIn("bge_rerank_leader_was_superseded", viewer)
        self.assertIn("deepseek_listwise_final", viewer)
        self.assertNotIn("manifest.status", viewer)

    def test_manifest_contract_requires_the_exact_frozen_paths(self) -> None:
        manifest = self.accepted_contract_manifest()
        self.assertEqual("a" * 40, validate_manifest_contract(manifest))
        manifest["required_paths"] = {**manifest["required_paths"], "substitute_path": True}
        with self.assertRaises(DemoContractError):
            validate_manifest_contract(manifest)

    def test_evidence_schemas_preserve_acceptance_and_screenshot_gates(self) -> None:
        root = Path(__file__).resolve().parents[1]
        run_schema = json.loads((root / "packages" / "evidence-schema" / "run-manifest.schema.json").read_text(encoding="utf-8"))
        screenshot_schema = json.loads((root / "packages" / "evidence-schema" / "screenshot-manifest.schema.json").read_text(encoding="utf-8"))
        self.assertIn("acceptance", run_schema["properties"])
        self.assertIn("required_paths", run_schema["required"])
        self.assertEqual(1, screenshot_schema["properties"]["screenshots"]["minItems"])
        self.assertFalse(screenshot_schema["additionalProperties"])

    def test_candidate_promotion_screenshot_and_verification_are_one_identity_chain(self) -> None:
        run_id = "order-api-field-migration-20260803T120000Z"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "demo"
            fixture = root / "scenarios" / SCENARIO_ID / "fixtures" / "manifest.json"
            fixture.parent.mkdir(parents=True)
            write_json(fixture, {"schema_version": 1, "query": {}, "documents": []})
            (root / ".gitignore").write_text(".runs/\n", encoding="utf-8")
            for command in (
                ["git", "init", "-b", "main"],
                ["git", "config", "user.name", "Demo Test"],
                ["git", "config", "user.email", "demo-test@example.invalid"],
                ["git", "add", "."],
                ["git", "commit", "-m", "test fixture"],
            ):
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            candidate = root / ".runs" / run_id
            target = {"release": RELEASE, "release_commit": RELEASE_COMMIT, "source_revision": SOURCE_REVISION, "container_digest": "sha256:" + "1" * 64, "demo_commit": commit}
            provider = {"provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/v1", "local_generative_llm": False}
            cleanup = {"namespaces_removed": True, "containers_removed": True, "ports_released": True, "runtime_secret_removed": True}
            pricing = {"observed_at": "2026-08-03T12:00:00Z", "official_url": "https://api-docs.deepseek.com/quick_start/pricing", "model": "deepseek-v4-flash", "currency": "USD", "prices_per_million_tokens": {"input_cache_miss": 0.1, "output": 0.2}}
            manifest = {
                "schema_version": 1,
                "run_id": run_id,
                "scenario_id": SCENARIO_ID,
                "state": "candidate",
                "target_identity": target,
                "fixture_manifest_sha256": sha256_file(fixture),
                "provider_identity": provider,
                "required_paths": {name: True for name in REQUIRED_PATH_NAMES},
                "cleanup": cleanup,
                "cost": {"budget_usd": 1.0, "within_budget_contract": True, "public_cost_claim_allowed": False, "usage_visibility": "partial", "model": "deepseek-v4-flash", "observable_input_tokens": 1, "observable_output_tokens": 1, "observable_call_count_minimum": 5, "pricing_snapshot": pricing},
                "assertions": {name: True for name in ("run_a", "run_b", "required_paths", "resolver", "cleanup", "budget", "model_checksums", "all_passed")},
                "run_a": {"path": "run-a/pgvector-result.json", "pass": True},
                "run_b": {"path": "run-b/summary.json", "pass": True, "serial_query_count": 2},
                "resolver": {"path": "run-b/resolver-01.json", "pass": True},
                "screenshot_eligible": False,
                "human_review_required": True,
                "claim_boundary": "Runtime evidence for this accepted scenario only.",
                "disclosed_gaps": [{"id": "partial-usage", "note": "Only observable provider usage is recorded."}],
            }
            source_identity = {
                "cortrix_release": RELEASE,
                "cortrix_release_commit": RELEASE_COMMIT,
                "cortrix_source_revision": SOURCE_REVISION,
                "container_image": "cortrix-demo:test",
                "container_digest": target["container_digest"],
                "demo_commit": commit,
                "demo_branch": "main",
                "demo_working_tree": "clean",
            }
            files = {
                "run-manifest.json": manifest,
                "source-manifest.json": {"run_id": run_id, "source": source_identity, "provider": provider, "private_source_paths_recorded": False, "secret_recorded": False},
                "runtime.json": {"run_id": run_id, "llm": {**provider, "secret_persisted_in_evidence": False}},
                "contract-smoke.json": {"provider": "deepseek", "model": "deepseek-v4-flash", "call_count": 1, "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "response_content_recorded": False},
                "model-checksums.json": {"all_match": True},
                "cleanup-receipt.json": {"run_id": run_id, **cleanup},
                "state-history.json": {"run_id": run_id, "transitions": [{"state": "created"}, {"state": "running"}, {"state": "candidate"}]},
                "run-a/pgvector-result.json": {"run_id": run_id, "pass": True},
                "run-b/summary.json": {"run_id": run_id, "pass": True},
                "run-b/resolver-01.json": self.layered_resolver(run_id),
                "run-b/resolver-02.json": self.layered_resolver(run_id),
            }
            for relative, value in files.items():
                write_json(candidate / relative, value)
            staged = stage_accepted(root, run_id, "OUTPUT-TEST-ACCEPTANCE")
            self.assertEqual("accepted_staged", staged["status"])
            screenshot = root / "viewer.png"
            screenshot.write_bytes(self.png_bytes())
            record_screenshot(root, run_id, screenshot, "/packages/viewer/index.html", "run-b/resolver-01.json")
            verified = verify_accepted(root, run_id)
            self.assertEqual("pass", verified["status"])
            accepted_text = "\n".join(path.read_text(encoding="utf-8") for path in (root / "scenarios" / SCENARIO_ID / "evidence").rglob("*.json"))
            self.assertNotIn("OUTPUT-TEST-ACCEPTANCE", accepted_text)


if __name__ == "__main__":
    unittest.main()
