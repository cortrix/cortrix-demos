from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "runtime" / "harness" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HarnessRuntimeTests(unittest.TestCase):
    def test_model_assets_have_public_pinned_sources_and_checksums(self) -> None:
        manifest = json.loads((ROOT / "runtime" / "model-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("4c0f0f96b652d5662a66d047771826a4d2933739", manifest["cortrix_source_commit"])
        self.assertFalse(manifest["redistributes_model_weights"])
        self.assertEqual(4, len(manifest["assets"]))
        for asset in manifest["assets"]:
            with self.subTest(component=asset["component"]):
                for key in ("source_repository", "source_revision", "source_path", "size_bytes", "sha256", "upstream_repository", "upstream_revision", "license"):
                    self.assertTrue(asset[key])
                self.assertEqual(40, len(asset["source_revision"]))
                self.assertEqual(64, len(asset["sha256"]))
        model_doc = (ROOT / "docs" / "model-assets.md").read_text(encoding="utf-8")
        self.assertIn("deploy/download-models.sh", model_doc)
        self.assertIn("--network none", model_doc)
        self.assertNotIn("does not contain a public, checksum-reproducible export recipe", model_doc)

    def test_fixture_loader_accepts_all_frozen_corpora(self) -> None:
        loader = load_script("harness_fixture_loader", "load-fixtures.py")
        counts = {"database-change-conflict-guardian": 12, "api-version-drift-coding-agent": 12, "payment-incident-shift-handoff": 16, "migration-decision-recovery": 21}
        for scenario, count in counts.items():
            with self.subTest(scenario=scenario):
                _, manifest = loader.load_manifest(ROOT, scenario)
                self.assertEqual(count, len(manifest["documents"]))
        for position in ("front", "middle", "end"):
            _, manifest = loader.load_manifest(ROOT, "migration-decision-recovery", position)
            stream = next(item for item in manifest["documents"] if item["document_id"] == "migration-task-event-stream")
            self.assertEqual(position, stream["version"])

    def test_campaign_reviews_worst_case_cost_before_external_work(self) -> None:
        campaign = load_script("harness_campaign", "run-campaign.py")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pricing.json"
            path.write_text(json.dumps({
                "official_url": "https://api-docs.deepseek.com/quick_start/pricing",
                "observed_at": "2026-08-17T00:00:00Z",
                "model": "deepseek-v4-flash",
                "currency": "USD",
                "prices_per_million_tokens": {"input_cache_hit": 0.1, "input_cache_miss": 0.2, "output": 0.4},
            }), encoding="utf-8")
            _, bound = campaign.require_pricing(path)
            self.assertLess(bound, 1.0)
            value = json.loads(path.read_text(encoding="utf-8"))
            value["prices_per_million_tokens"]["output"] = 1_000
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(campaign.CampaignFailure):
                campaign.require_pricing(path)

    def test_campaign_caps_model_answers_and_disables_cortrix_llm(self) -> None:
        campaign = load_script("harness_campaign_static", "run-campaign.py")
        compose = (ROOT / "runtime" / "harness" / "docker-compose.yml").read_text(encoding="utf-8")
        answer_runner = (ROOT / "runtime" / "harness" / "run-answer.py").read_text(encoding="utf-8")
        self.assertEqual(4, campaign.ANSWER_CALLS)
        self.assertEqual(2_048, campaign.MAX_OUTPUT_TOKENS_PER_ANSWER)
        self.assertIn('CORTRIX_LLM_ENABLED: "false"', compose)
        self.assertIn("maxTokens: 2048", answer_runner)
        self.assertIn("thinking: disabled", answer_runner)
        campaign_source = (ROOT / "runtime" / "harness" / "run-campaign.py").read_text(encoding="utf-8")
        self.assertIn("verify_volume_models", campaign_source)
        self.assertIn("--network", campaign_source)
        self.assertIn("containers_absent", campaign_source)
        self.assertIn("runtime_secret_materialized", campaign_source)
        continuity = campaign.load_campaign_contract(ROOT / "runtime" / "harness" / "campaigns" / "operational-continuity.json")
        self.assertEqual(8, continuity["answer_calls"])
        self.assertEqual(1.0, continuity["budget_usd"])
        self.assertEqual(["front", "middle", "end"], continuity["scenarios"][1]["position_variants"])

    def test_campaign_resolves_compose_before_the_paid_contract_smoke(self) -> None:
        campaign = load_script("harness_campaign_compose", "run-campaign.py")

        def fake_run(command, **_kwargs):
            if command[:2] == ["docker", "compose"]:
                return subprocess.CompletedProcess(command, 1, "", "docker: unknown command: docker compose")
            if command == ["docker-compose", "version"]:
                return subprocess.CompletedProcess(command, 0, "Docker Compose version 5.1.4", "")
            self.fail(f"unexpected command: {command}")

        with patch.object(campaign.subprocess, "run", side_effect=fake_run):
            command, label = campaign.require_compose(ROOT)
        self.assertEqual(["docker-compose"], command)
        self.assertEqual("docker-compose", label)

        source = (ROOT / "runtime" / "harness" / "run-campaign.py").read_text(encoding="utf-8")
        self.assertLess(source.index("compose_command, compose_label = require_compose(root)"), source.index("smoke_result = contract_smoke"))

    def test_campaign_verifies_volume_write_access_before_the_paid_contract_smoke(self) -> None:
        campaign = load_script("harness_campaign_volume", "run-campaign.py")
        with patch.object(campaign, "execute", return_value=subprocess.CompletedProcess([], 0, "", "")) as execute:
            result = campaign.verify_volume_runtime_access(ROOT, "goal-volume")
        command = execute.call_args.args[0]
        self.assertIn("goal-volume:/data", command)
        self.assertEqual(["-c", "test -w /data"], command[-2:])
        self.assertTrue(result["runtime_user_can_write_data"])

        with patch.object(campaign, "execute", side_effect=campaign.CampaignFailure("exit 1")):
            with self.assertRaisesRegex(campaign.CampaignFailure, "data volume is not writable"):
                campaign.verify_volume_runtime_access(ROOT, "goal-volume")

        source = (ROOT / "runtime" / "harness" / "run-campaign.py").read_text(encoding="utf-8")
        self.assertLess(source.index("volume_access = verify_volume_runtime_access"), source.index("smoke_result = contract_smoke"))

    def test_campaign_loads_the_complete_headless_runtime_before_paid_work(self) -> None:
        campaign = load_script("harness_campaign_headless", "run-campaign.py")
        with TemporaryDirectory() as directory:
            harness_root = Path(directory)
            for relative in campaign.HEADLESS_RUNTIME_EXPORTS:
                path = harness_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("export {};\n", encoding="utf-8")

            def fake_execute(command, **kwargs):
                self.assertEqual(["--profile", "headless", "--help"], command[-3:])
                environment = kwargs["environment"]
                self.assertNotIn("DEEPSEEK_API_KEY", environment)
                self.assertNotIn("DEEPSEEK_BASE_URL", environment)
                self.assertNotIn("CORTRIX_LLM_SECRET_FILE", environment)
                self.assertEqual("1", environment["DSH_TELEMETRY_DISABLED"])
                self.assertEqual("read-only", environment["DSH_PERMISSION_MODE"])
                return subprocess.CompletedProcess(command, 0, "Usage: dsh --profile headless\n", "")

            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "must-not-be-used", "DEEPSEEK_BASE_URL": "https://invalid.example", "CORTRIX_LLM_SECRET_FILE": "/private/profile"}, clear=False), patch.object(campaign, "execute", side_effect=fake_execute):
                result = campaign.verify_harness_headless_runtime(ROOT, harness_root)

            self.assertTrue(result["runtime_exports_present"])
            self.assertTrue(result["headless_help_loaded"])
            self.assertEqual(0, result["external_calls"])
            self.assertEqual(0, result["session_artifacts"])

            (harness_root / campaign.HEADLESS_RUNTIME_EXPORTS[1]).unlink()
            with self.assertRaisesRegex(campaign.CampaignFailure, "packages/typert/registry/lib/index.js"):
                campaign.verify_harness_headless_runtime(ROOT, harness_root)

        source = (ROOT / "runtime" / "harness" / "run-campaign.py").read_text(encoding="utf-8")
        self.assertLess(source.index("headless_runtime = verify_harness_headless_runtime"), source.index("smoke_result = contract_smoke"))

    def test_campaign_runs_a_zero_llm_source_projection_probe_before_paid_work(self) -> None:
        campaign = load_script("harness_campaign_source_probe", "run-campaign.py")
        source = (ROOT / "runtime" / "harness" / "run-campaign.py").read_text(encoding="utf-8")
        self.assertLess(source.index("source_projection = run_source_projection_probe"), source.index("smoke_result = contract_smoke"))
        self.assertIn('tool_result.get("external_llm_calls") != 0', source)
        self.assertIn('fixture_operation(root, scenario, namespace, cleanup_path, cleanup=True)', source)
        self.assertEqual("5b43a744c2fa93ddb95715b7783943757eb64b4e", campaign.PLUGIN_COMMIT)

    def test_curated_usage_uses_a_path_free_session_artifact_label(self) -> None:
        answer = load_script("harness_answer_usage", "run-answer.py")
        source = (ROOT / "runtime" / "harness" / "run-answer.py").read_text(encoding="utf-8")
        self.assertEqual("deepseek-harness-session-jsonl", answer.DURABLE_SESSION_ARTIFACT)
        self.assertNotIn("relative_to(home).as_posix()", source)
        self.assertNotIn("/", answer.DURABLE_SESSION_ARTIFACT)
        self.assertNotIn("\\", answer.DURABLE_SESSION_ARTIFACT)

    def test_campaign_fails_immediately_when_the_cortrix_container_exits(self) -> None:
        campaign = load_script("harness_campaign_readiness", "run-campaign.py")
        with patch.object(campaign, "urlopen", side_effect=OSError("connection refused")), patch.object(campaign, "exited_campaign_containers", return_value=True):
            with self.assertRaisesRegex(campaign.CampaignFailure, "exited before readiness"):
                campaign.wait_ready(ROOT, timeout_seconds=1)

    def test_plugin_query_uses_real_tool_runtime_and_exact_surface(self) -> None:
        source = (ROOT / "runtime" / "harness" / "query-plugin.mjs").read_text(encoding="utf-8")
        for fragment in ("ctx.plugin(systemPrompt.default)", "ctx.plugin(tools.default)", "cortrix_search_evidence", "cortrix_get_source", "durable_session_events"):
            self.assertIn(fragment, source)

    def test_manual_runbooks_use_the_real_runtime_interfaces(self) -> None:
        for scenario in ("database-change-conflict-guardian", "api-version-drift-coding-agent"):
            with self.subTest(scenario=scenario):
                root = ROOT / "scenarios" / scenario / "docs"
                run_a = (root / "run-a-frozen-workspace-evidence-step-by-step.md").read_text(encoding="utf-8")
                run_b = (root / "run-b-cortrix-plugin-step-by-step.md").read_text(encoding="utf-8")
                self.assertIn("runtime/harness/run-answer.py", run_a)
                self.assertNotIn("test -n \"${DEEPSEEK_API_KEY", run_a)
                self.assertIn("--output \"$RUN_ROOT/ingestion.json\"", run_b)
                self.assertIn("--query-file", run_b)
                self.assertIn("harness project-cortrix", run_b)
                self.assertIn("git clone https://github.com/deepseek-ai/deepseek-harness.git", run_b)
                self.assertIn("npx --yes pnpm@11.7.0 --dir .runtime/deepseek-harness run build:lib:host", run_b)
                self.assertIn("for SERIAL in 1 2", run_b)
                self.assertIn("runtime/harness/run-answer.py", run_b)
                self.assertNotIn("--receipt", run_b)
        continuity = {
            "payment-incident-shift-handoff": "run-a-frozen-shift-snapshot-step-by-step.md",
            "migration-decision-recovery": "run-a-intermediate-conclusion-step-by-step.md",
        }
        for scenario, run_a_name in continuity.items():
            root = ROOT / "scenarios" / scenario / "docs"
            run_a = (root / run_a_name).read_text(encoding="utf-8")
            run_b = (root / "run-b-cortrix-plugin-step-by-step.md").read_text(encoding="utf-8")
            self.assertIn("./democtl validate", run_a)
            self.assertIn("./democtl harness baseline", run_a)
            self.assertIn("./democtl harness verify-accepted", run_b)
            self.assertIn("evidence-01.json", run_b)

    def test_agent_cli_exposes_the_complete_harness_lifecycle(self) -> None:
        completed = subprocess.run([str(ROOT / "democtl"), "harness", "--help"], cwd=ROOT, check=True, capture_output=True, text=True)
        for command in ("campaign", "record-clean-room-pass", "stage-accepted", "record-screenshot", "verify-accepted"):
            self.assertIn(command, completed.stdout)


if __name__ == "__main__":
    unittest.main()
