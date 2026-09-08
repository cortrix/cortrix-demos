from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from cortrix_demo_runner.catalog import describe_scenario, list_scenarios, load_adapter_profile, load_agent_manifest, load_external_call_policy, scenario_integration_kind, validate_catalog
from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.io import write_json
from cortrix_demo_runner.scenario import validate_scenario


ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_first_time_agent_has_a_safe_root_bootstrap(self) -> None:
        manifest = load_agent_manifest(ROOT)
        self.assertEqual("accepted_replay", manifest["agent_first"]["default_mode"])
        self.assertFalse(manifest["agent_first"]["default_external_calls"])
        self.assertTrue(manifest["agent_first"]["fail_closed"])
        self.assertEqual(
            [
                "./democtl list --json",
                "./democtl describe --scenario order-api-field-migration --json",
                "./democtl validate --scenario order-api-field-migration",
                "./democtl describe --scenario order-api-live-three-path --json",
                "./democtl validate --scenario order-api-live-three-path",
                "./democtl verify-accepted",
            ],
            manifest["bootstrap"]["safe_default"],
        )
        instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Agent Bootstrap", instructions)
        for command in manifest["bootstrap"]["safe_default"]:
            self.assertIn(command, instructions)
        self.assertEqual("./democtl prepare-image --scenario order-api-field-migration", manifest["gates"]["live_full_stack"]["image_preparation"])
        self.assertEqual("runtime/image-provenance.json", manifest["catalogs"]["image_provenance"])

    def test_agent_can_discover_and_describe_the_accepted_scenario(self) -> None:
        scenarios = list_scenarios(ROOT)
        self.assertIn("order-api-field-migration", [item["id"] for item in scenarios])
        description = describe_scenario(ROOT, "order-api-field-migration")
        self.assertEqual("accepted", description["accepted_evidence"]["status"])
        self.assertEqual("postgresql-pgvector", description["technology_profile"]["baseline"]["adapter_id"])
        self.assertEqual("deepseek-openai-compatible", description["technology_profile"]["llm"]["adapter_id"])
        self.assertEqual(1.0, description["external_call_policy"]["budget_usd"])
        self.assertEqual("discover", description["lifecycle"][0])
        self.assertEqual("cleanup", description["lifecycle"][-1])
        self.assertEqual("required", description["review_gates"]["independent_clean_run"])
        self.assertEqual(["remote_publication"], description["review_gates"]["human_review_required_for"])
        self.assertEqual("sealed_full_stack_v1", scenario_integration_kind(scenarios[0]))

    def test_contract_only_adapter_fails_before_runtime_work(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "not implemented") as captured:
            load_adapter_profile(ROOT, "baseline", "elasticsearch", require_implemented=True)
        self.assertEqual("CX_DEMO_ADAPTER_UNSUPPORTED", captured.exception.code)
        self.assertFalse(captured.exception.retryable)

    def test_unknown_scenario_has_a_structured_agent_error(self) -> None:
        with self.assertRaises(DemoContractError) as captured:
            describe_scenario(ROOT, "missing-scenario")
        payload = captured.exception.as_dict()
        self.assertEqual("CX_DEMO_SCENARIO_NOT_FOUND", payload["error"]["code"])
        self.assertEqual("permanent", payload["error"]["category"])
        self.assertFalse(payload["error"]["retryable"])
        self.assertEqual("missing-scenario", payload["error"]["structured_data"]["scenario_id"])
        self.assertIn("next_action", payload["error"]["structured_data"])

    def test_temporary_second_scenario_passes_catalog_and_scenario_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cortrix-demos"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".runtime", ".runs", "__pycache__", "*.pyc"))
            second_id = "support-api-field-migration"
            source = root / "scenarios" / "order-api-field-migration"
            target = root / "scenarios" / second_id
            shutil.copytree(source, target)

            registry_path = root / "scenarios" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            entry = dict(registry["scenarios"][0])
            entry.update(
                {
                    "id": second_id,
                    "display_name": "Support API Field Migration",
                    "scenario_contract": f"{second_id}/scenario.json",
                    "validation_contract": f"{second_id}/expected/validation.json",
                    "technology_profile": f"{second_id}/profiles/technology-profile.json",
                    "human_guide": f"{second_id}/README.md",
                    "accepted_pointer": f"{second_id}/evidence/accepted-run.json",
                }
            )
            registry["scenarios"].append(entry)
            write_json(registry_path, registry)

            scenario_path = target / "scenario.json"
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["id"] = second_id
            scenario["display_name"] = "Support API Field Migration"
            write_json(scenario_path, scenario)

            validation_path = target / "expected" / "validation.json"
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            validation["scenario_id"] = second_id
            validation["evidence_contract"]["run_id_pattern"] = rf"^{second_id}-[0-9]{{8}}T[0-9]{{6}}Z(?:-retry)?$"
            write_json(validation_path, validation)

            assertions_path = target / "expected" / "assertions.json"
            assertions = json.loads(assertions_path.read_text(encoding="utf-8"))
            assertions["scenario_id"] = second_id
            write_json(assertions_path, assertions)

            technology_path = target / "profiles" / "technology-profile.json"
            technology = json.loads(technology_path.read_text(encoding="utf-8"))
            technology["scenario_id"] = second_id
            write_json(technology_path, technology)

            self.assertEqual([], validate_scenario(root, second_id))
            self.assertEqual([], validate_catalog(root))
            self.assertEqual({"order-api-field-migration", "order-api-live-three-path", second_id}, {item["id"] for item in list_scenarios(root)})

    def test_external_call_policy_is_fail_closed_at_one_dollar(self) -> None:
        policy = load_external_call_policy(ROOT)
        self.assertEqual(1.0, policy["budget_usd"])
        self.assertFalse(policy["local_generative_fallback_allowed"])

    def test_cli_discovery_and_error_outputs_are_json(self) -> None:
        listing = subprocess.run([str(ROOT / "democtl"), "list", "--json"], cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertEqual("order-api-field-migration", json.loads(listing.stdout)["scenarios"][0]["id"])
        accepted = subprocess.run([str(ROOT / "democtl"), "verify-accepted"], cwd=ROOT, check=True, capture_output=True, text=True)
        accepted_payload = json.loads(accepted.stdout)
        self.assertEqual("pass", accepted_payload["status"])
        self.assertEqual("archive_integrity", accepted_payload["proof_scope"])
        self.assertFalse(accepted_payload["live_reexecution"])
        missing = subprocess.run([str(ROOT / "democtl"), "describe", "--scenario", "missing", "--json"], cwd=ROOT, check=False, capture_output=True, text=True)
        self.assertEqual(1, missing.returncode)
        self.assertEqual("CX_DEMO_SCENARIO_NOT_FOUND", json.loads(missing.stderr)["error"]["code"])

    def test_license_logo_and_provenance_are_present(self) -> None:
        self.assertIn("Apache License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / "NOTICE").is_file())
        logo = (ROOT / "assets" / "brand" / "logo-full-dark.svg").read_text(encoding="utf-8")
        self.assertIn("aria-label=\"Cortrix\"", logo)
        self.assertIn("#FF6405", logo)
        self.assertTrue((ROOT / "docs" / "provenance.md").is_file())

    def test_human_run_guides_and_repository_structure_are_discoverable(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Agent-first by design", readme)
        self.assertIn("## How the repository is organized", readme)
        for relative_path in (
            "scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector.md",
            "scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack.md",
            "scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector-step-by-step.md",
            "scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack-step-by-step.md",
        ):
            self.assertIn(relative_path, readme)
            self.assertTrue((ROOT / relative_path).is_file())
        run_a = (ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-a-postgresql-pgvector.md").read_text(encoding="utf-8")
        run_b = (ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-b-cortrix-full-stack.md").read_text(encoding="utf-8")
        numbered_heading = re.compile(r"^## [0-9]+\. ")
        self.assertEqual(
            [line for line in run_a.splitlines() if numbered_heading.match(line)],
            [line for line in run_b.splitlines() if numbered_heading.match(line)],
        )
        self.assertIn("The combined workflow executes Run A first and Run B second", run_a)
        self.assertIn("The combined workflow executes Run A first and Run B second", run_b)
        self.assertIn("`account_id`", run_a)
        self.assertIn("`buyer_account_id`", run_b)
        self.assertIn("independent Clean Run acceptance", run_b)
        run_a_pipeline = (ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-a-postgresql-pgvector-step-by-step.md").read_text(encoding="utf-8")
        run_b_pipeline = (ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-b-cortrix-full-stack-step-by-step.md").read_text(encoding="utf-8")
        accepted_run_id = json.loads((ROOT / "scenarios" / "order-api-field-migration" / "evidence" / "accepted-run.json").read_text(encoding="utf-8"))["run_id"]
        self.assertIn(f"accepted run is `{accepted_run_id}`", run_a)
        self.assertIn(f"accepted run is `{accepted_run_id}`", run_b)
        self.assertIn(f"accepted run `{accepted_run_id}`", run_a_pipeline)
        self.assertIn(f"accepted run `{accepted_run_id}`", run_b_pipeline)
        manual_heading = re.compile(r"^## [0-9]+\. ")
        self.assertEqual(
            [line for line in run_a_pipeline.splitlines() if manual_heading.match(line)],
            [line for line in run_b_pipeline.splitlines() if manual_heading.match(line)],
        )
        self.assertNotIn("./democtl", run_a_pipeline)
        self.assertNotIn("./democtl", run_b_pipeline)
        query_command = "python3 -c 'from pathlib import Path; print(Path(\"scenarios/order-api-field-migration/fixtures/query.txt\").read_text().strip())'"
        self.assertIn(query_command, run_a_pipeline)
        self.assertIn(query_command, run_b_pipeline)
        for fragment in ("set -euo pipefail", "org.opencontainers.image.revision", "docker-compose", "psql -X", "embedding <=>", "extract_vectors.py", "/documents/tasks/", "/progress"):
            self.assertIn(fragment, run_a_pipeline)
        for fragment in ("set -euo pipefail", "org.opencontainers.image.revision", "config/external-call-policy.json", "math.isfinite", "conservative_bound_usd", "cortrix.full-stack.yaml", "/documents", "/query?explain=true", "deepseek-v4-flash", "inspect_namespace.py", "selected_content_contains_expected_field", "f35_contextualization_failures", "unset CORTRIX_LLM_API_KEY DEEPSEEK_API_KEY"):
            self.assertIn(fragment, run_b_pipeline)
        self.assertIn("API readiness does not guarantee", run_b_pipeline)
        self.assertIn("listens on loopback inside the Cortrix container", run_b_pipeline)
        self.assertIn("METRICS_READY=0", run_b_pipeline)
        self.assertIn("METRICS_AFTER_READY=0", run_b_pipeline)
        self.assertIn("metrics-before-ingest.prom.tmp", run_b_pipeline)
        self.assertIn("metrics-after-ingest.prom.tmp", run_b_pipeline)
        metrics_command = "docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix curl -fsS --max-time 10 http://127.0.0.1:9091/metrics"
        self.assertEqual(2, run_b_pipeline.count(metrics_command))
        self.assertNotIn("curl -fsS --max-time 10 http://127.0.0.1:19091/metrics", run_b_pipeline)
        self.assertEqual(2, run_b_pipeline.count("for _ in $(seq 1 60); do"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Demo observability versus production operation", readme)
        self.assertIn("not a required Cortrix production interface", readme)
        self.assertIn("Humans can use the paired manual Runbooks", readme)

    def test_manual_runbooks_fail_closed_on_source_and_pricing_drift(self) -> None:
        def bash_block(text: str, needle: str) -> str:
            needle_position = text.index(needle)
            start = text.rfind("```bash\n", 0, needle_position) + len("```bash\n")
            end = text.index("\n```", needle_position)
            return text[start:end]

        runbook_paths = (
            ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-a-postgresql-pgvector-step-by-step.md",
            ROOT / "scenarios" / "order-api-field-migration" / "docs" / "run-b-cortrix-full-stack-step-by-step.md",
        )
        for path in runbook_paths:
            text = path.read_text(encoding="utf-8")
            block = bash_block(text, "org.opencontainers.image.revision")
            self.assertLess(block.index("set -euo pipefail"), block.index("git -C .runtime/cortrix-src checkout"))
            self.assertIn("git -C .runtime/cortrix-src rev-parse HEAD", block)
            source_guard = block[block.index('SOURCE_HEAD="'):block.index("if ! docker image inspect")]
            source_guard = re.sub(r'^SOURCE_HEAD=.*$', 'SOURCE_HEAD="wrong"', source_guard, count=1, flags=re.MULTILINE)
            source_result = subprocess.run(["bash", "-c", "set -euo pipefail\n" + source_guard], check=False, capture_output=True, text=True)
            self.assertNotEqual(0, source_result.returncode)
            image_guard = block[block.index('IMAGE_REVISION="'):]
            image_guard = re.sub(r'^IMAGE_REVISION=.*$', 'IMAGE_REVISION="wrong"', image_guard, count=1, flags=re.MULTILINE)
            image_result = subprocess.run(["bash", "-c", "set -euo pipefail\n" + image_guard], check=False, capture_output=True, text=True)
            self.assertNotEqual(0, image_result.returncode)

        run_b_text = runbook_paths[1].read_text(encoding="utf-8")
        pricing_block = bash_block(run_b_text, "Pricing values must be finite and non-negative")
        python_start = pricing_block.index("python3 - <<'PY'\n") + len("python3 - <<'PY'\n")
        python_end = pricing_block.index("\nPY", python_start)
        pricing_code = pricing_block[python_start:python_end]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pricing-snapshot.json"
            pricing_code = pricing_code.replace('Path(".runs/manual-cortrix/pricing-snapshot.json")', f"Path({str(output)!r})")
            base_environment = {
                **os.environ,
                "DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M": "0.0028",
                "DEEPSEEK_OUTPUT_USD_PER_M": "0.28",
            }
            for invalid_value in ("nan", "-0.14"):
                result = subprocess.run(
                    [sys.executable, "-c", pricing_code],
                    cwd=ROOT,
                    env={**base_environment, "DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M": invalid_value},
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, result.returncode)
            valid = subprocess.run(
                [sys.executable, "-c", pricing_code],
                cwd=ROOT,
                env={**base_environment, "DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M": "0.14"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, valid.returncode, valid.stderr)
            self.assertEqual(0.042, json.loads(output.read_text(encoding="utf-8"))["conservative_bound_usd"])

    def test_run_b_manual_metrics_capture_retries_empty_replies(self) -> None:
        runbook = (
            ROOT
            / "scenarios"
            / "order-api-field-migration"
            / "docs"
            / "run-b-cortrix-full-stack-step-by-step.md"
        ).read_text(encoding="utf-8")
        needle = "METRICS_READY=0"
        needle_position = runbook.index(needle)
        block_start = runbook.rfind("```bash\n", 0, needle_position) + len("```bash\n")
        block_end = runbook.index("\n```", needle_position)
        block = runbook[block_start:block_end]
        metrics_command = "docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix curl -fsS --max-time 10 http://127.0.0.1:9091/metrics"
        self.assertIn(metrics_command, block)
        block = block[block.index(needle):]
        block = block.replace(metrics_command, "fake_curl").replace("sleep 2", ":")

        with tempfile.TemporaryDirectory() as directory:
            script = f"""
set -euo pipefail
mkdir -p .runs/manual-cortrix
printf '0\n' > counter
fake_curl() {{
  count="$(cat counter)"
  count="$((count + 1))"
  printf '%s\n' "$count" > counter
  if [ "$count" -eq 1 ]; then
    return 52
  fi
  printf 'cortrix_test_metric 1\n'
}}
{block}
test "$(cat counter)" = 2
grep -qx 'cortrix_test_metric 1' .runs/manual-cortrix/metrics-before-ingest.prom
test ! -e .runs/manual-cortrix/metrics-before-ingest.prom.tmp
"""
            result = subprocess.run(
                ["bash", "-c", script],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
