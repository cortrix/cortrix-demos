"""Keyless tests for isolation, identity, and failure behavior."""

import json
from pathlib import Path
import sys
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch


from cortrix_live_demo import engines
RUN = "run_0123456789abcdef"


class EngineConfig:
    embedding_port = 18426
    full_port = 18427

    @staticmethod
    def container_name(component):
        return "cortrix-live-demo-" + component


ENGINE_CONFIG = EngineConfig()


class EngineTests(unittest.TestCase):
    def test_run_and_arm_isolation_rejects_sql_or_path_injection(self):
        identities = {engines.namespace_for(RUN, arm) for arm in ("a0", "a1", "pg", "b")}
        self.assertEqual(len(identities), 4)
        for run, arm in (("run_../x", "a0"), (RUN, "a0;drop"), ("run_0123456789ABCDEf", "b")):
            with self.assertRaises(engines.EngineError):
                engines.namespace_for(run, arm)
        with self.assertRaises(engines.EngineError):
            engines.schema_name('cx_bad";DROP SCHEMA public;')

    def test_resolver_never_fills_expected_field_from_fixture(self):
        self.assertEqual(engines.extract_field("No identifier evidence"), "unknown")
        self.assertEqual(engines.extract_field("account_id and buyer_account_id"), "unknown")
        rows = [{"rank": 1, "document_id": "old", "lifecycle_status": "superseded", "content": "Use `account_id`."}, {"rank": 2, "document_id": "new", "lifecycle_status": "current", "content": "Use `buyer_account_id`."}]
        self.assertEqual(engines.resolve_candidates(rows, lifecycle=False)["selected_field"], "account_id")
        self.assertEqual(engines.resolve_candidates(rows, lifecycle=True)["selected_field"], "buyer_account_id")
        self.assertEqual(engines.resolve_candidates(rows[:1], lifecycle=True)["status"], "unknown")

    def test_named_resolvers_preserve_public_policy_semantics(self):
        rows = [{"rank": 1, "document_id": "old", "lifecycle_status": "superseded", "content": "account_id"}, {"rank": 2, "document_id": "new", "lifecycle_status": "current", "content": "buyer_account_id"}]
        self.assertEqual(engines.resolve_vector_first(rows), engines.resolve_candidates(rows, lifecycle=False))
        self.assertEqual(engines.resolve_current_candidates(rows), engines.resolve_candidates(rows, lifecycle=True))
        self.assertEqual(engines.pg_current_filter("a0"), "")
        self.assertEqual(engines.pg_current_filter("a1"), " WHERE lifecycle_status='current'")

    def test_input_hash_and_duplicate_identity_fail_before_operations(self):
        file = {"document_id": "doc", "content": "text", "sha256": engines.content_hash("text")}
        engines.validate_files([file])
        with self.assertRaises(engines.EngineError):
            engines.validate_files([file, file])
        with self.assertRaises(engines.EngineError):
            engines.validate_files([{**file, "content": "changed"}])

    def test_cancel_check_prevents_initial_runtime_access(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        engine._metrics = Mock()
        check = Mock(side_effect=RuntimeError("cancelled"))
        file = {"document_id": "doc", "content": "text", "sha256": engines.content_hash("text")}
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            engine.ingest(RUN, "a0", [file], "question", Mock(), check)
        engine._metrics.assert_not_called()

    def test_pg_current_filter_runs_in_sql_and_keeps_native_order(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        vector = [1.0] + [0.0] * 1023
        engine._export = Mock(return_value=[{"document_id": "query-anchor", "embedding": vector, "embedding_sha256": "hash"}])
        engine._sql_json = Mock(return_value=[{"document_id": "new", "lifecycle_status": "current", "content": "buyer_account_id", "score": 0.4}])
        result = engine._pg_query(engines.namespace_for(RUN, "a1"), "a1", Mock(), Mock())
        self.assertIn("WHERE lifecycle_status='current'", engine._sql_json.call_args.args[0])
        self.assertIn("LIMIT 8", engine._sql_json.call_args.args[0])
        self.assertEqual(result["ranking"][0]["score"], 0.4)
        self.assertEqual(result["resolver"]["selected_field"], "buyer_account_id")

    def test_pg_assist_runs_after_native_ranking_for_current_policy_only(self):
        vector = [1.0] + [0.0] * 1023
        assist = Mock(return_value=[{"rank": 1, "document_id": "assisted", "lifecycle_status": "current", "content": "buyer_account_id", "score": 0.8}])
        engine = engines.Engines(config=ENGINE_CONFIG, pg_assist=assist)
        engine._export = Mock(return_value=[{"document_id": "query-anchor", "embedding": vector, "embedding_sha256": "hash"}])
        engine._sql_json = Mock(return_value=[{"document_id": "native", "lifecycle_status": "current", "content": "account_id", "score": 0.4}])
        record = Mock()
        result = engine._pg_query(engines.namespace_for(RUN, "a1"), "a1", record, Mock(), run_id=RUN, question="Which field?")
        self.assertEqual(result["resolver"]["selected_document_id"], "assisted")
        self.assertEqual(assist.call_args.args[:3], (RUN, "a1", "Which field?"))
        self.assertEqual(assist.call_args.args[3][0]["document_id"], "native")
        self.assertIn("pg_native_ranking", [call.args[0] for call in record.call_args_list])

        assist.reset_mock()
        engine._pg_query(engines.namespace_for(RUN, "a0"), "a0", Mock(), Mock(), run_id=RUN, question="Which field?")
        assist.assert_not_called()
        self.assertNotIn("LIMIT 8", engine._sql_json.call_args.args[0])

    def test_ingest_records_each_real_pg_business_step(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        file = {"document_id": "doc", "content": "text", "sha256": engines.content_hash("text")}
        vector = {"block_id": "block", "document_id": "doc", "chunk_index": 0, "content": "text", "embedding": [1.0] + [0.0] * 1023, "embedding_sha256": "hash"}
        engine._metrics = Mock(return_value="")
        engine._namespace = Mock()
        engine._durable = Mock(return_value={"documents": [], "text_blocks": []})
        engine._upload = Mock()
        engine._export = Mock(side_effect=[[vector], [{**vector, "document_id": "query-anchor"}]])
        engine._pg_write = Mock(return_value={"row_count": 1})
        engine._embedding_receipt = Mock(return_value={})
        events = []
        engine.ingest(RUN, "a0", [file], "Which field?", lambda stage, value: events.append((stage, value)), Mock())
        business = [(stage, value["step_id"], value["owner"]) for stage, value in events if stage.startswith("business_step_")]
        self.assertEqual(business, [
            ("business_step_started", "namespace_prepare", "cortrix"),
            ("business_step_completed", "namespace_prepare", "cortrix"),
            ("business_step_started", "documents_ingest", "cortrix"),
            ("business_step_completed", "documents_ingest", "cortrix"),
            ("business_step_started", "query_anchor_ingest", "cortrix"),
            ("business_step_completed", "query_anchor_ingest", "cortrix"),
            ("business_step_started", "vectors_export", "application"),
            ("business_step_completed", "vectors_export", "application"),
            ("business_step_started", "pg_write", "postgresql"),
            ("business_step_completed", "pg_write", "postgresql"),
        ])

    def test_ingest_records_b_enrichment_as_one_business_step(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        file = {"document_id": "doc", "content": "text", "sha256": engines.content_hash("text")}
        engine._metrics = Mock(return_value="")
        engine._namespace = Mock()
        engine._durable = Mock(return_value={"documents": [], "text_blocks": []})
        engine._upload = Mock()
        engine._wait_enrichment = Mock(return_value={"ready": True})
        engine._embedding_receipt = Mock(return_value={})
        events = []
        engine.ingest(RUN, "b", [file], "Which field?", lambda stage, value: events.append((stage, value)), Mock())
        step_ids = [value["step_id"] for stage, value in events if stage == "business_step_completed"]
        self.assertEqual(step_ids, ["namespace_prepare", "documents_ingest", "enrichment_wait"])

    def test_pg_reconciliation_rejects_another_input_before_write(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        engine._pg_snapshot = Mock(return_value={"row_count": 1, "rows": [{"document_id": "other", "fixture_sha256": "wrong", "block_id": "1", "chunk_index": 0, "content": "old"}]})
        engine._sql = Mock()
        with self.assertRaises(engines.ReconciliationRequired):
            engine._pg_write(engines.namespace_for(RUN, "a0"), [{"document_id": "doc", "sha256": "correct"}], [{"block_id": "2", "document_id": "doc", "chunk_index": 0, "content": "new"}], Mock(), Mock())
        engine._sql.assert_not_called()

    def test_completed_task_failure_fields_are_not_accepted(self):
        engine = engines.Engines(config=ENGINE_CONFIG, poll_interval=0)
        engine._durable = Mock(return_value={"documents": [], "text_blocks": []})
        engine._http = Mock(side_effect=[(202, {"task_id": "operation-one"}), (200, {"status": "completed", "error_code": "failed"})])
        item = {"document_id": "doc", "sha256": "hash", "content": "text", "name": "doc.md"}
        record = Mock()
        with self.assertRaises(engines.EngineError):
            engine._upload("embedding", engines.namespace_for(RUN, "a0"), item, record, Mock())
        self.assertEqual(sum(call.args[1] == "POST" for call in engine._http.call_args_list), 1)
        self.assertEqual([call.args[0] for call in record.call_args_list[:2]], ["document_submitting", "document_task_accepted"])

    def test_cleanup_refuses_pending_enrichment_and_never_runs_compose(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        engine.snapshot = Mock(return_value={})
        engine._durable = Mock(return_value={"documents": [], "enrich_states": [{"status": "pending"}]})
        engine._http = Mock()
        engine._sql = Mock()
        with self.assertRaises(engines.ReconciliationRequired):
            engine.cleanup(RUN, "b", Mock())
        engine._http.assert_not_called()
        engine._sql.assert_not_called()

    def test_invalid_vector_cannot_reach_pg(self):
        with self.assertRaises(engines.EngineError):
            engines.vector_literal([0.0] * 1024)
        with self.assertRaises(engines.EngineError):
            engines.vector_literal([float("nan")] + [0.0] * 1023)

    def test_http_timeout_is_not_retried(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        with patch.object(engines.urllib.request, "urlopen", side_effect=TimeoutError("uncertain")) as call:
            with self.assertRaises(engines.ReconciliationRequired):
                engine._http("full", "POST", "/documents", {"content": "text"})
        self.assertEqual(call.call_count, 1)

    def test_http_query_trace_headers_preserve_the_business_payload(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        body = {"query": "Which field?", "namespaces": [engines.namespace_for(RUN, "b")]}
        trace = {"session_id": engines.namespace_for(RUN, "b"), "trace_id": "unit-trace"}
        response = Mock(status=200)
        response.read.return_value = b'{}'
        with patch.object(engines.urllib.request, "urlopen", return_value=nullcontext(response)) as call:
            engine._http("full", "POST", "/query", body, trace=trace)
        request = call.call_args.args[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["x-session-id"], trace["session_id"])
        self.assertEqual(headers["x-trace-id"], trace["trace_id"])
        self.assertEqual(headers["x-agent-id"], "cortrix_demo")
        self.assertEqual(json.loads(request.data), body)

    def test_pending_task_blocks_duplicate_upload(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        namespace = engines.namespace_for(RUN, "a0")
        engine.restore_pending_tasks(namespace, ["operation-one"])
        engine._http = Mock(return_value=(200, {"status": "running"}))
        engine._durable = Mock()
        with self.assertRaises(engines.ReconciliationRequired):
            engine._upload("embedding", namespace, {"document_id": "doc"}, Mock(), Mock())
        engine._durable.assert_not_called()
        self.assertEqual(engine._http.call_args.args[1], "GET")

    def test_pg_absence_uses_json_boolean_and_does_not_query_missing_table(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        engine._sql = Mock(return_value="false\n")
        result = engine._pg_snapshot(engines.namespace_for(RUN, "pg"))
        self.assertFalse(result["exists"])
        self.assertIn("to_json", engine._sql.call_args.args[0])
        self.assertEqual(engine._sql.call_count, 1)

    def test_cortrix_preserves_native_scores_and_unknown_identity(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        engine._metrics = Mock(side_effect=["cortrix_reranker_score_duration_seconds_count 0", "cortrix_reranker_score_duration_seconds_count 1"])
        response = {"results": [{"child_id": "unmapped", "score": 0.93, "rerank_score": 0.07, "content": "An unrelated result"}, {"child_id": "child", "score": 0.3, "rerank_score": 0.99, "content": "buyer_account_id"}], "explain": {"llm_dependent_features": {"rag_fusion": {"active": True}, "llm_rerank": {"active": True}}}}
        response["meta"] = {"namespaces_failed": [], "coverage_ratio": 1, "namespaces_succeeded": [engines.namespace_for(RUN, "b")]}
        engine._http = Mock(return_value=(200, response))
        engine._durable = Mock(return_value={"documents": [{"doc_id": "d1", "metadata": {"document_id": "current"}}], "text_blocks": [{"child_id": "child", "doc_id": "d1"}]})
        files = [{"document_id": "current", "status": "current", "content": "Use buyer_account_id."}]
        result = engine._cortrix_query(engines.namespace_for(RUN, "b"), files, "Which buyer field?", Mock(), Mock())
        self.assertIsNone(result["ranking"][0]["document_id"])
        self.assertEqual([r["score"] for r in result["ranking"]], [0.93, 0.3])
        self.assertEqual(result["resolver"]["selected_rank"], 2)
        self.assertEqual(result["request"]["top_k"], 8)
        self.assertEqual(result["trace_context"]["session_id"], engines.namespace_for(RUN, "b"))
        self.assertEqual(engine._http.call_args.kwargs["trace"], result["trace_context"])

    def test_http_success_with_partial_query_is_not_accepted(self):
        engine = engines.Engines(config=ENGINE_CONFIG)
        engine._metrics = Mock(return_value="")
        engine._durable = Mock(return_value={"documents": [], "text_blocks": []})
        engine._http = Mock(return_value=(200, {"results": [], "error": {"code": "CX_ERR_SCATTER_TIMEOUT"}, "meta": {"coverage_ratio": 0, "namespaces_failed": [{"namespace": "failed"}], "namespaces_succeeded": []}}))
        record = Mock()
        with self.assertRaisesRegex(engines.EngineError, "incomplete query"):
            engine._cortrix_query(engines.namespace_for(RUN, "b"), [], "query", record, Mock())
        stages = [call.args[0] for call in record.call_args_list]
        self.assertIn("business_step_completed", stages)
        self.assertIn("business_step_failed", stages)

    def test_permanent_enrichment_failure_is_terminal(self):
        engine = engines.Engines(config=ENGINE_CONFIG, task_timeout=.1, poll_interval=0)
        engine._metrics = Mock(return_value="")
        engine._durable = Mock(return_value={"documents": [], "text_blocks": [], "enrich_states": [{"status": "failed_permanent"}], "block_counts": {}})
        with self.assertRaisesRegex(engines.EngineError, "recorded a failure"):
            engine._wait_enrichment(engines.namespace_for(RUN, "b"), [], "", Mock(), Mock())


if __name__ == "__main__":
    unittest.main()
