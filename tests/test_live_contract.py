from __future__ import annotations

import http.client
import unittest
from unittest.mock import patch

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.live import failure_category, ingestion_completion, pricing_cost, require_budget_bound
from cortrix_demo_runner.runtime import request


PRICING = {
    "prices_per_million_tokens": {
        "input_cache_hit": 0.1,
        "input_cache_miss": 0.5,
        "output": 1.0,
    }
}


class LiveContractTests(unittest.TestCase):
    def test_observable_cost_uses_cache_miss_input_rate(self) -> None:
        self.assertEqual(0.0025, pricing_cost(PRICING, 3000, 1000))

    def test_budget_bound_rejects_price_increase_without_expanding_budget(self) -> None:
        profile = {"budget_usd": 1.0, "max_full_stack_attempts": 2, "budget_guard": {"maximum_input_tokens": 1_000_000, "maximum_output_tokens": 1_000_000}}
        with self.assertRaisesRegex(DemoContractError, "exceed USD 1.00"):
            require_budget_bound(profile, PRICING)

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
