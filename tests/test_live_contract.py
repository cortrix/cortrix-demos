from __future__ import annotations

import http.client
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.io import read_json, write_json
from cortrix_demo_runner.live import attempt_ledger, execute_once, failure_category, ingestion_completion, pricing_cost, query_payload, record_query_observation, require_budget_bound, reserve_attempt, update_attempt, validate_reviewed_attempt_limit
from cortrix_demo_runner.runtime import request


PRICING = {
    "prices_per_million_tokens": {
        "input_cache_hit": 0.1,
        "input_cache_miss": 0.5,
        "output": 1.0,
    }
}
ROOT = Path(__file__).resolve().parents[1]


class LiveContractTests(unittest.TestCase):
    def test_query_payload_uses_the_reviewed_chunk_granularity(self) -> None:
        payload = query_payload("example", "chunk")
        self.assertEqual("chunk", payload["granularity"])
        self.assertEqual(4, payload["top_k"])
        self.assertEqual(4, payload["llm_rerank_config"]["top_n"])

    def test_execute_once_rejects_scenario_drift_before_attempt_or_external_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "scenarios", root / "scenarios")
            path = root / "scenarios" / "order-api-field-migration" / "scenario.json"
            scenario = read_json(path)
            scenario["retrieval_contract"]["query_granularity"] = "both"
            write_json(path, scenario)
            with self.assertRaisesRegex(DemoContractError, "Scenario validation failed.*chunk-only"):
                execute_once(root, root / "missing-source", root / "missing-pricing.json", "order-api-field-migration-20260803T120000Z")
            self.assertFalse((root / ".runs").exists())

    def test_observable_cost_uses_cache_miss_input_rate(self) -> None:
        self.assertEqual(0.0025, pricing_cost(PRICING, 3000, 1000))

    def test_budget_bound_rejects_price_increase_without_expanding_budget(self) -> None:
        profile = {"budget_usd": 5.0, "max_full_stack_attempts": 2, "budget_guard": {"maximum_input_tokens": 5_000_000, "maximum_output_tokens": 5_000_000}}
        with self.assertRaisesRegex(DemoContractError, "exceed USD 5.00"):
            require_budget_bound(profile, PRICING)

    def test_reviewed_fourth_attempt_uses_four_attempt_budget_bound(self) -> None:
        profile = {"budget_usd": 5.0, "max_full_stack_attempts": 2, "budget_guard": {"maximum_input_tokens": 200_000, "maximum_output_tokens": 50_000}}
        pricing = {"prices_per_million_tokens": {"input_cache_miss": 0.14, "output": 0.28}}
        self.assertEqual(0.168, require_budget_bound(profile, pricing, reviewed_attempt_limit=4))

    def test_reviewed_fifth_attempt_uses_five_attempt_budget_bound(self) -> None:
        profile = {"budget_usd": 5.0, "max_full_stack_attempts": 2, "budget_guard": {"maximum_input_tokens": 200_000, "maximum_output_tokens": 50_000}}
        pricing = {"prices_per_million_tokens": {"input_cache_miss": 0.14, "output": 0.28}}
        self.assertEqual(0.21, require_budget_bound(profile, pricing, reviewed_attempt_limit=5))

    def test_fifth_attempt_requires_five_limit_and_sixth_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reserve_attempt(root, "attempt-1")
            update_attempt(root, "attempt-1", "rejected", "timeout")
            reserve_attempt(root, "attempt-2")
            update_attempt(root, "attempt-2", "rejected", "timeout")
            self.assertEqual(3, reserve_attempt(root, "attempt-3", reviewed_attempt_limit=3))
            update_attempt(root, "attempt-3", "rejected", "deterministic_or_contract_failure")
            self.assertEqual(4, reserve_attempt(root, "attempt-4", reviewed_attempt_limit=4))
            with self.assertRaisesRegex(DemoContractError, "reviewed 4-attempt"):
                reserve_attempt(root, "attempt-5", reviewed_attempt_limit=4)
            self.assertEqual(5, reserve_attempt(root, "attempt-5", reviewed_attempt_limit=5))
            with self.assertRaisesRegex(DemoContractError, "reviewed 5-attempt"):
                reserve_attempt(root, "attempt-6", reviewed_attempt_limit=5)

    def test_reviewed_attempt_limit_cannot_exceed_five(self) -> None:
        with self.assertRaisesRegex(DemoContractError, "must be 2, 3, 4, or 5"):
            validate_reviewed_attempt_limit(6)

    def test_new_campaign_ledger_is_isolated_from_the_legacy_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reserve_attempt(root, "legacy-1")
            campaign_id = "order-api-field-migration-2.x"
            self.assertEqual(1, reserve_attempt(root, "campaign-1", reviewed_attempt_limit=4, campaign_id=campaign_id, scenario_version="2.0.0", demo_commit="a" * 40))
            self.assertEqual(1, len(attempt_ledger(root)["full_stack_attempts"]))
            campaign = attempt_ledger(root, campaign_id)
            self.assertEqual(campaign_id, campaign["campaign_id"])
            self.assertEqual("2.0.0", campaign["full_stack_attempts"][0]["scenario_version"])

    def test_query_observation_is_persisted_before_resolver_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            record_query_observation(
                run_dir,
                1,
                {"query": "example"},
                {"results": [{"child_id": "unmapped"}]},
                "before\n",
                "after\n",
            )
            self.assertTrue((run_dir / "run-b" / "query-01.request.json").is_file())
            self.assertTrue((run_dir / "run-b" / "query-01.response.json").is_file())
            self.assertEqual("before\n", (run_dir / "run-b" / "query-01.metrics.before.prom").read_text())
            self.assertEqual("after\n", (run_dir / "run-b" / "query-01.metrics.after.prom").read_text())

    def test_only_named_transient_categories_are_retryable(self) -> None:
        self.assertEqual("http_429", failure_category(DemoContractError("request failed. transient_category=http_429")))
        self.assertEqual("timeout", failure_category(DemoContractError("readiness failed. transient_category=timeout")))
        self.assertEqual("deterministic_or_contract_failure", failure_category(DemoContractError("resolver failed")))

    def test_local_remote_disconnect_becomes_a_readiness_retryable_contract_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=http.client.RemoteDisconnected("closed")):
            with self.assertRaisesRegex(DemoContractError, "closed the connection before an HTTP response"):
                request("GET", "/system/health/ready")

    def test_ingestion_completion_uses_all_durable_blocks_not_an_unrelated_demo_constant(self) -> None:
        evidence = {
            "f03_llm_enriched_chunks": 2,
            "f35_contextualized_chunks": 2,
            "hype_questions": 6,
            "document_summaries": 2,
            "enrich_state_ok": 2,
        }
        durable = {"text_blocks": [{"child_id": "a"}, {"child_id": "b"}]}
        result = ingestion_completion(evidence, durable, expected_document_count=2, hype_questions_per_chunk=3)
        self.assertTrue(result["pass"])
        self.assertEqual(2, result["expected_text_block_count"])
        self.assertEqual(6, result["expected_hype_question_count"])

    def test_ingestion_completion_rejects_any_unfinished_actual_block(self) -> None:
        evidence = {
            "f03_llm_enriched_chunks": 2,
            "f35_contextualized_chunks": 1,
            "hype_questions": 6,
            "document_summaries": 2,
            "enrich_state_ok": 2,
        }
        durable = {"text_blocks": [{"child_id": "a"}, {"child_id": "b"}]}
        result = ingestion_completion(evidence, durable, expected_document_count=2, hype_questions_per_chunk=3)
        self.assertFalse(result["pass"])
        self.assertFalse(result["checks"]["f35_all_chunks"])


if __name__ == "__main__":
    unittest.main()
