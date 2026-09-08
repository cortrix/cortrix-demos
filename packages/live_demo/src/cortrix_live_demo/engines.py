"""Real, isolated PostgreSQL and Cortrix adapters for the live demo.

The caller owns scheduling, durable checkpoints, budget authorization, and runtime
provisioning. This module never starts services or substitutes synthetic results.
The mounted vector helper and SQLite layout require verification against RC2.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable

from .operation_timing import timed_attempt
from .config import RuntimeConfig, load_config


Record = Callable[[str, dict[str, Any]], None]
Check = Callable[[], None]
PgAssist = Callable[[str, str, str, list[dict[str, Any]], Record, Check], list[dict[str, Any]]]
RUN_PATTERN = re.compile(r"^run_[a-f0-9]{16}$")
NAMESPACE_PATTERN = re.compile(r"^cx_[a-f0-9]{16}_(?:a0|a1|pg|b)(?:_q)?$")
PATHS = {"a0", "a1", "pg", "b"}
SUCCESS = {"ready", "completed", "success", "succeeded"}
FAILURE = {"failed", "cancelled", "canceled", "error"}
PG_ASSIST_CANDIDATE_LIMIT = 8


class EngineError(RuntimeError):
    """A real operation failed or the observed runtime broke its contract."""


class ReconciliationRequired(EngineError):
    """Existing data cannot safely be treated as a completed prior step."""


def namespace_for(run_id: str, path: str, *, query: bool = False) -> str:
    if not RUN_PATTERN.fullmatch(run_id) or path not in PATHS:
        raise EngineError("Invalid run or path identity")
    return "cx_" + run_id[4:] + "_" + path + ("_q" if query else "")


def sql_quote(value: object) -> str:
    text = str(value)
    if "\x00" in text:
        raise EngineError("NUL is not allowed in SQL text")
    return "'" + text.replace("'", "''") + "'"


def schema_name(value: str) -> str:
    if not NAMESPACE_PATTERN.fullmatch(value):
        raise EngineError("Invalid PostgreSQL schema identity")
    return '"' + value + '"'


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_files(files: list[dict[str, Any]]) -> None:
    if not 1 <= len(files) <= 8:
        raise EngineError("A run requires one to eight input files")
    ids: set[str] = set()
    for item in files:
        if not isinstance(item.get("content"), str) or not item["content"].strip():
            raise EngineError("An input file has no text content")
        identity = item.get("document_id")
        if not isinstance(identity, str) or not identity or identity in ids:
            raise EngineError("Input document identities must be unique nonempty strings")
        ids.add(identity)
        if item.get("sha256") != content_hash(item["content"]):
            raise EngineError("Input content does not match its frozen SHA256")


def vector_literal(vector: list[Any]) -> str:
    if len(vector) != 1024 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
        raise EngineError("Embedding must contain 1024 finite numeric values")
    if not 0.999 <= math.sqrt(sum(v * v for v in vector)) <= 1.001:
        raise EngineError("Embedding is not L2 normalized")
    return "[" + ",".join(format(float(v), ".9g") for v in vector) + "]"


def extract_field(content: str) -> str:
    """Only identify an unambiguous identifier actually present in evidence."""
    identifiers = set(re.findall(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*_id)(?![A-Za-z0-9_])", content))
    return next(iter(identifiers)) if len(identifiers) == 1 else "unknown"


def _resolution(selected: dict[str, Any] | None, policy: str) -> dict[str, Any]:
    text = "\n".join(str(selected.get(key) or "") for key in ("content", "parent_content")) if selected else ""
    return {
        "owner": "demo_application_policy",
        "policy": policy,
        "selected_document_id": selected.get("document_id", "unknown") if selected else "unknown",
        "selected_field": extract_field(text),
        "selected_rank": selected.get("rank") if selected else None,
        "status": "resolved" if selected and selected.get("document_id") and extract_field(text) != "unknown" else "unknown",
    }


def resolve_vector_first(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the A0 first-result policy without reordering candidates."""
    return _resolution(candidates[0] if candidates else None, "first_in_returned_order")


def resolve_current_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the current-version policy while preserving returned order."""
    eligible = [item for item in candidates if item.get("lifecycle_status") == "current"]
    return _resolution(eligible[0] if eligible else None, "first_current_in_returned_order")


def resolve_candidates(candidates: list[dict[str, Any]], *, lifecycle: bool) -> dict[str, Any]:
    """Preserve the public resolver contract while exposing each policy."""
    return resolve_current_candidates(candidates) if lifecycle else resolve_vector_first(candidates)


def pg_current_filter(path: str) -> str:
    """Return the existing lifecycle predicate for PG-backed paths."""
    return " WHERE lifecycle_status='current'" if path in {"a1", "pg"} else ""


# Read-only SQLite inspection also validates the mounted runtime's actual schema.
DURABLE_SCRIPT = r'''
import hashlib, json, pathlib, sqlite3, sys
p = pathlib.Path(sys.argv[1])
if not p.is_file():
    print(json.dumps({"exists": False, "documents": [], "text_blocks": [], "enrich_states": [], "block_counts": {}}))
    raise SystemExit(0)
c = sqlite3.connect("file:" + str(p) + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
try:
    docs = [dict(r) for r in c.execute("SELECT doc_id,source_path,metadata_json,status,deleted_at FROM documents ORDER BY doc_id")]
    for d in docs:
        d["source_name"] = pathlib.Path(d.pop("source_path")).name
        d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
    blocks = [dict(r) for r in c.execute("SELECT child_id,doc_id,chunk_index,content_text AS content,contextualized_status FROM blocks WHERE block_type=1 ORDER BY doc_id,chunk_index,block_id")]
    states = [dict(r) for r in c.execute("SELECT child_id,doc_id,status,attempts,last_error FROM enrich_state ORDER BY doc_id,child_id")]
    counts = {str(r[0]):r[1] for r in c.execute("SELECT block_type,count(*) FROM blocks GROUP BY block_type")}
finally:
    c.close()
v = {"exists": True,"documents": docs,"text_blocks": blocks,"enrich_states": states,"block_counts": counts}
v["content_sha256"] = hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
print(json.dumps(v,ensure_ascii=False))
'''


class Engines:
    def __init__(self, *, runtime_identity: dict[str, Any] | None = None, task_timeout: float = 900, poll_interval: float = 1, pg_assist: PgAssist | None = None, config: RuntimeConfig | None = None):
        self.config = config or load_config()
        self.runtime_identity = dict(runtime_identity or {})
        self.task_timeout = task_timeout
        self.poll_interval = poll_interval
        self.pg_assist = pg_assist
        self.containers = {component: self.config.container_name(component) for component in ("embedding", "full", "pg")}
        self.api_bases = {"embedding": f"http://127.0.0.1:{self.config.embedding_port}/api/v1", "full": f"http://127.0.0.1:{self.config.full_port}/api/v1"}
        self.pending_tasks: dict[str, set[str]] = {}
        self.uncertain_namespaces: set[str] = set()

    def restore_pending_tasks(self, namespace: str, task_ids: list[str]) -> None:
        """Restore caller-owned task receipts before resuming or cleaning a run."""
        schema_name(namespace)
        if any(not isinstance(task, str) or not task for task in task_ids):
            raise EngineError("Restored task identities must be nonempty strings")
        self.pending_tasks.setdefault(namespace, set()).update(task_ids)

    def _emit(self, record: Record, stage: str, started: float, **data: Any) -> None:
        record(stage, {"source": "live_runtime", "runtime_identity": self.runtime_identity, "duration_ms": round((time.monotonic() - started) * 1000, 3), **data})

    def _command(self, args: list[str], *, input_text: str | None = None, timeout: float = 180) -> str:
        result = subprocess.run(args, input=input_text, capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode:
            raise EngineError(json.dumps({"operation": args[:4], "exit_code": result.returncode, "stderr": result.stderr, "stdout": result.stdout}, ensure_ascii=False))
        return result.stdout

    def _http(self, arm: str, method: str, endpoint: str, body: dict[str, Any] | None = None, *, expected: set[int] | None = None, timeout: float = 180, trace: dict[str, str] | None = None) -> tuple[int, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if trace is not None:
            headers.update({"X-Session-Id": trace["session_id"], "X-Trace-Id": trace["trace_id"], "X-Agent-Id": "cortrix_demo"})
        request = urllib.request.Request(self.api_bases[arm] + endpoint, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, raw = response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise ReconciliationRequired(f"{method} {endpoint} has an uncertain outcome: {error}") from error
        try:
            value = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            value = {"raw_response": raw}
        if status not in (expected or {200}):
            raise EngineError(json.dumps({"method": method, "endpoint": endpoint, "http_status": status, "response": value}, ensure_ascii=False))
        return status, value

    def _sql(self, sql: str) -> str:
        return self._command(["docker", "exec", "-i", self.containers["pg"], "psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-U", "cortrix_demo", "-d", "cortrix_demo"], input_text="SET standard_conforming_strings=on;\n" + sql)

    def _sql_json(self, sql: str) -> Any:
        return json.loads(self._sql(sql).strip())

    def _durable(self, arm: str, namespace: str) -> dict[str, Any]:
        schema_name(namespace)
        raw = self._command(["docker", "exec", self.containers[arm], "python3", "-c", DURABLE_SCRIPT, f"/data/units/unit-{namespace}/store.db"])
        return json.loads(raw)

    def _metrics(self, arm: str) -> str:
        return self._command(["docker", "exec", self.containers[arm], "curl", "-fsS", "http://127.0.0.1:9091/metrics"])

    @staticmethod
    def _metric_values(raw: str) -> dict[str, float]:
        values: dict[str, float] = {}
        for line in raw.splitlines():
            if not line or line.startswith("#"):
                continue
            try:
                key, value = line.rsplit(" ", 1)
                values[key] = float(value)
            except ValueError:
                continue
        return values

    def _embedding_receipt(self, arm: str, before: str, *, require_inference: bool) -> dict[str, Any]:
        after = self._metrics(arm)
        old, new = self._metric_values(before), self._metric_values(after)
        count = new.get("cortrix_onnx_inference_duration_seconds_count", 0) - old.get("cortrix_onnx_inference_duration_seconds_count", 0)
        active = new.get('cortrix_onnx_embedding_active_ep{ep="cpu"}') == 1
        if not active or (require_inference and count <= 0):
            raise EngineError("Actual CPU ONNX inference metrics are absent; verify the RC2 metrics contract")
        return {"metrics_before": before, "metrics_after": after, "onnx_inference_delta": count, "embedding_active_cpu": active}

    def _namespace(self, arm: str, namespace: str, record: Record, check: Check) -> None:
        check()
        started = time.monotonic()
        status, response = self._http(arm, "GET", "/namespaces/" + namespace, expected={200, 404})
        if status == 404:
            check()
            status, response = self._http(arm, "POST", "/namespaces", {"name": namespace, "display_name": namespace}, expected={201})
        self._emit(record, "namespace_ready", started, namespace=namespace, http_status=status, response=response)

    def _upload(self, arm: str, namespace: str, item: dict[str, Any], record: Record, check: Check) -> None:
        check()
        started = time.monotonic()
        if namespace in self.uncertain_namespaces:
            raise ReconciliationRequired("A prior upload outcome is unknown; do not submit another document")
        for task_id in list(self.pending_tasks.get(namespace, set())):
            _, progress = self._http(arm, "GET", "/documents/tasks/" + urllib.parse.quote(task_id, safe="") + "/progress")
            self._emit(record, "document_task_reconciled", started, namespace=namespace, task_id=task_id, response=progress)
            if str(progress.get("status", "")).lower() not in SUCCESS or progress.get("error_code") or progress.get("error_msg"):
                raise ReconciliationRequired("A prior task has not successfully completed; do not submit another document")
            self.pending_tasks[namespace].discard(task_id)
            check()
        before = self._durable(arm, namespace)
        matching = [doc for doc in before["documents"] if doc["metadata"].get("document_id") == item["document_id"]]
        if matching:
            valid = len(matching) == 1 and matching[0]["metadata"].get("fixture_sha256") == item["sha256"] and not matching[0].get("deleted_at")
            blocks = [b for b in before["text_blocks"] if b["doc_id"] == matching[0]["doc_id"]]
            if not valid or not blocks or str(matching[0].get("status", "")).lower() not in SUCCESS | {"active", "indexed"}:
                raise ReconciliationRequired("Existing document is incomplete or its identity differs; inspect the recorded task before resubmitting")
            self._emit(record, "document_reconciled", started, namespace=namespace, document_id=item["document_id"], sha256=item["sha256"], reused=True, durable=before)
            return
        metadata = {key: item[key] for key in ("document_id", "version", "status", "effective_at") if key in item}
        metadata.update({"fixture_sha256": item["sha256"], "demo_run_id": "run_" + namespace.split("_")[1], "input_id": item.get("id")})
        body = {"namespace": namespace, "filename": str(item.get("name") or item["document_id"]).replace("\\", "/").split("/")[-1], "content": item["content"], "metadata": metadata}
        check()
        self.uncertain_namespaces.add(namespace)
        self._emit(record, "document_submitting", started, namespace=namespace, document_id=item["document_id"], sha256=item["sha256"])
        status, accepted = self._http(arm, "POST", "/documents", body, expected={202})
        self._emit(record, "document_task_accepted", started, namespace=namespace, document_id=item["document_id"], sha256=item["sha256"], http_status=status, response=accepted, before=before)
        task_id = accepted.get("task_id") if isinstance(accepted, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise ReconciliationRequired("Accepted upload has no task_id; do not repeat the POST")
        self.uncertain_namespaces.discard(namespace)
        self.pending_tasks.setdefault(namespace, set()).add(task_id)
        deadline = time.monotonic() + self.task_timeout
        while time.monotonic() < deadline:
            check()
            _, progress = self._http(arm, "GET", "/documents/tasks/" + urllib.parse.quote(task_id, safe="") + "/progress")
            self._emit(record, "document_task_progress", started, namespace=namespace, task_id=task_id, response=progress)
            state = str(progress.get("status", "")).lower()
            if state in SUCCESS | FAILURE:
                self.pending_tasks[namespace].discard(task_id)
            if state in FAILURE or progress.get("error_code") or progress.get("error_msg"):
                raise EngineError("Document task failed: " + json.dumps(progress, ensure_ascii=False))
            if state in SUCCESS:
                check()
                after = self._durable(arm, namespace)
                self._emit(record, "document_written", started, namespace=namespace, task_id=task_id, document_id=item["document_id"], sha256=item["sha256"], after=after)
                documents = [d for d in after["documents"] if d["metadata"].get("document_id") == item["document_id"] and d["metadata"].get("fixture_sha256") == item["sha256"] and not d.get("deleted_at")]
                if len(documents) != 1 or not any(b["doc_id"] == documents[0]["doc_id"] for b in after["text_blocks"]):
                    raise ReconciliationRequired("Successful task has no uniquely matching durable document and text blocks")
                return
            check()
            time.sleep(self.poll_interval)
        raise ReconciliationRequired(f"Document task {task_id} remains unresolved after timeout")

    def _export(self, namespace: str, record: Record, check: Check) -> list[dict[str, Any]]:
        check()
        started = time.monotonic()
        schema_name(namespace)
        output = f"/data/{namespace}_vectors.json"
        self._command(["docker", "exec", self.containers["embedding"], "python3", "/demo-helpers/extract_vectors.py", "--db", f"/data/units/unit-{namespace}/store.db", "--wal", f"/data/units/unit-{namespace}/hnsw.wal", "--dimension", "1024", "--output", output])
        check()
        raw = self._command(["docker", "exec", self.containers["embedding"], "cat", output])
        data = json.loads(raw)
        records = [item for item in data.get("records", []) if item.get("block_type") == 1]
        if not records or not data.get("wal_sha256"):
            raise EngineError("Vector export contains no verified text blocks")
        for item in records:
            vector_literal(item["embedding"])
            actual = hashlib.sha256(struct.pack("<1024f", *item["embedding"])).hexdigest()
            if actual != item.get("embedding_sha256"):
                raise EngineError("Vector content does not match the helper's SHA256")
        self._emit(record, "vectors_exported", started, namespace=namespace, output=output, export_sha256=content_hash(raw), wal_sha256=data["wal_sha256"], records=records, dependency="Cortrix embedding-only parsing, chunking and BGE-M3 inference")
        return records

    def _pg_snapshot(self, namespace: str) -> dict[str, Any]:
        schema = schema_name(namespace)
        exists = self._sql_json("SELECT to_json(to_regclass(" + sql_quote(namespace + ".semantic_blocks") + ") IS NOT NULL);")
        if not exists:
            return {"exists": False, "schema": namespace, "row_count": 0, "rows": []}
        rows = self._sql_json(f"SELECT coalesce(json_agg(row_to_json(r)), '[]'::json) FROM (SELECT block_id,document_id,chunk_index,lifecycle_status,fixture_sha256,content,embedding::text::json AS embedding,md5(embedding::text) AS embedding_md5 FROM {schema}.semantic_blocks ORDER BY document_id,chunk_index,block_id) r;")
        for row in rows:
            embedding = row.pop("embedding")
            vector_literal(embedding)
            row["embedding_sha256"] = hashlib.sha256(struct.pack("<1024f", *embedding)).hexdigest()
        return {"exists": True, "schema": namespace, "row_count": len(rows), "rows": rows, "content_sha256": content_hash(json.dumps(rows, sort_keys=True, ensure_ascii=False))}

    def _pg_write(self, namespace: str, files: list[dict[str, Any]], vectors: list[dict[str, Any]], record: Record, check: Check) -> dict[str, Any]:
        check()
        started = time.monotonic()
        before = self._pg_snapshot(namespace)
        expected = {(f["document_id"], f["sha256"]) for f in files}
        if before["row_count"]:
            observed = {(row["document_id"], row["fixture_sha256"]) for row in before["rows"]}
            expected_blocks = {(str(v["block_id"]), v["document_id"], int(v["chunk_index"]), v.get("content") or "", v.get("embedding_sha256")) for v in vectors}
            observed_blocks = {(str(v["block_id"]), v["document_id"], int(v["chunk_index"]), v["content"], v.get("embedding_sha256")) for v in before["rows"]}
            if observed != expected or observed_blocks != expected_blocks:
                raise ReconciliationRequired("Existing PG rows do not exactly match this arm's frozen documents and exported blocks")
            self._emit(record, "pg_write_reconciled", started, before=before, reused=True)
            return before
        by_id = {item["document_id"]: item for item in files}
        inserts = []
        seen: set[str] = set()
        for vector in vectors:
            fixture = by_id.get(vector.get("document_id"))
            if not fixture:
                raise EngineError("Exported block does not belong to a frozen input document")
            seen.add(fixture["document_id"])
            fields = [sql_quote(vector["block_id"]), sql_quote(fixture["document_id"]), str(int(vector["chunk_index"])), sql_quote(fixture.get("version", "unknown")), sql_quote(fixture.get("status", "unknown")), sql_quote(fixture.get("effective_at", "")), sql_quote(fixture["sha256"]), sql_quote(vector.get("content") or ""), sql_quote(vector_literal(vector["embedding"])) + "::vector"]
            inserts.append("(" + ",".join(fields) + ")")
        if seen != set(by_id):
            raise EngineError("At least one input has no independent PG embedding")
        schema = schema_name(namespace)
        sql = f"BEGIN; CREATE EXTENSION IF NOT EXISTS vector; CREATE SCHEMA IF NOT EXISTS {schema}; CREATE TABLE IF NOT EXISTS {schema}.semantic_blocks (block_id text PRIMARY KEY, document_id text NOT NULL, chunk_index integer NOT NULL, version text NOT NULL, lifecycle_status text NOT NULL, effective_at text NOT NULL, fixture_sha256 text NOT NULL, content text NOT NULL, embedding vector(1024) NOT NULL); INSERT INTO {schema}.semantic_blocks VALUES {','.join(inserts)}; COMMIT;"
        check()
        self._sql(sql)
        check()
        after = self._pg_snapshot(namespace)
        expected_blocks = {(str(v["block_id"]), v["document_id"], v["embedding_sha256"]) for v in vectors}
        observed_blocks = {(str(v["block_id"]), v["document_id"], v["embedding_sha256"]) for v in after["rows"]}
        if after["row_count"] != len(inserts) or expected_blocks != observed_blocks:
            raise EngineError("PG durable identities and vectors do not match the independent export")
        environment = self._sql_json("SELECT json_build_object('server_version',current_setting('server_version'),'pgvector_version',(SELECT extversion FROM pg_extension WHERE extname='vector'));")
        self._emit(record, "pg_written", started, before=before, after=after, environment=environment, query_kind="native_psql", sql=sql)
        return after

    def _wait_enrichment(self, namespace: str, files: list[dict[str, Any]], before_metrics: str, record: Record, check: Check) -> dict[str, Any]:
        started = time.monotonic()
        deadline = started + self.task_timeout
        last_report = started - 10
        while time.monotonic() < deadline:
            check()
            durable = self._durable("full", namespace)
            count = len(durable["text_blocks"])
            states = durable["enrich_states"]
            checks = {"documents": {d["metadata"].get("document_id") for d in durable["documents"] if not d.get("deleted_at")} == {f["document_id"] for f in files}, "text_blocks": count >= len(files), "enrichment": sum(s["status"] == "ok" for s in states) >= count > 0, "hype": int(durable["block_counts"].get("16", 0)) >= 3 * count > 0, "summaries": int(durable["block_counts"].get("17", 0)) >= len(files)}
            after_metrics = self._metrics("full")
            old, new = self._metric_values(before_metrics), self._metric_values(after_metrics)
            failures = {key: new.get(key, 0) - old.get(key, 0) for key in ('cortrix_contextual_retrieval_chunks_total{status="failed"}', 'cortrix_hype_index_llm_calls_total{status="failed"}', 'cortrix_doc_summary_llm_calls_total{status="failed"}')}
            if time.monotonic() - last_report >= 10:
                self._emit(record, "enrichment_progress", started, namespace=namespace, durable=durable, checks=checks, metrics_before=before_metrics, metrics_after=after_metrics)
                last_report = time.monotonic()
            if any(value > 0 for value in failures.values()) or any(s["status"] in FAILURE | {"failed_permanent"} for s in states):
                self._emit(record, "enrichment_failed", started, durable=durable, metrics_before=before_metrics, metrics_after=after_metrics, failures=failures)
                raise EngineError("Full Stack enrichment recorded a failure")
            if all(checks.values()):
                self._emit(record, "enrichment_completed", started, namespace=namespace, durable=durable, checks=checks, metrics_before=before_metrics, metrics_after=after_metrics)
                return durable
            check()
            time.sleep(self.poll_interval)
        raise ReconciliationRequired("Full Stack enrichment is still incomplete; inspect durable tasks before continuing")

    def ingest(self, run_id: str, path: str, files: list[dict[str, Any]], question: str, record: Record, check: Check) -> dict[str, Any]:
        validate_files(files)
        namespace = namespace_for(run_id, path)
        if not question.strip():
            raise EngineError("A frozen question is required")
        arm = "full" if path == "b" else "embedding"
        started = time.monotonic()
        check()
        before_metrics = self._metrics(arm)
        with timed_attempt(record, "namespace_prepare", "ingest", "cortrix"):
            self._namespace(arm, namespace, record, check)
        before = self._durable(arm, namespace)
        frozen_ids = {item["document_id"] for item in files}
        if any(doc["metadata"].get("document_id") not in frozen_ids for doc in before["documents"]):
            raise ReconciliationRequired("Namespace contains documents outside this run's frozen input set")
        with timed_attempt(record, "documents_ingest", "ingest", "cortrix"):
            for item in files:
                self._upload(arm, namespace, item, record, check)
        if path == "b":
            with timed_attempt(record, "enrichment_wait", "ingest", "cortrix"):
                result = self._wait_enrichment(namespace, files, before_metrics, record, check)
        else:
            query_namespace = namespace_for(run_id, path, query=True)
            with timed_attempt(record, "query_anchor_ingest", "ingest", "cortrix"):
                self._namespace(arm, query_namespace, record, check)
                anchor = {"id": "query-anchor", "document_id": "query-anchor", "name": "query-anchor.txt", "content": question, "sha256": content_hash(question)}
                self._upload(arm, query_namespace, anchor, record, check)
            with timed_attempt(record, "vectors_export", "ingest", "application"):
                vectors = self._export(namespace, record, check)
                self._export(query_namespace, record, check)
            with timed_attempt(record, "pg_write", "ingest", "postgresql"):
                result = self._pg_write(namespace, files, vectors, record, check)
        check()
        inference = self._embedding_receipt(arm, before_metrics, require_inference=not before["text_blocks"])
        value = {"path": path, "namespace": namespace, "document_count": len(files), "result": result, "inference": inference, "embedding_dependency": "Cortrix embedding-only" if path != "b" else "Cortrix Full Stack"}
        self._emit(record, "ingest_completed", started, **value)
        return value

    def _pg_search(self, namespace: str, path: str, vector: str, check: Check) -> tuple[list[dict[str, Any]], str, str]:
        where = pg_current_filter(path)
        limit = f" LIMIT {PG_ASSIST_CANDIDATE_LIMIT}" if path in {"a1", "pg"} else ""
        sql = f"SELECT coalesce(json_agg(row_to_json(r)), '[]'::json) FROM (SELECT block_id,document_id,chunk_index,version,lifecycle_status,content,1-(embedding <=> {vector}) AS score FROM {schema_name(namespace)}.semantic_blocks{where} ORDER BY embedding <=> {vector},document_id,chunk_index{limit}) r;"
        check()
        rows = self._sql_json(sql)
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        return rows, sql, where

    def _pg_query(self, namespace: str, path: str, record: Record, check: Check, *, run_id: str | None = None, question: str | None = None) -> dict[str, Any]:
        started = time.monotonic()
        with timed_attempt(record, "query_vector_read", "query", "application"):
            query_records = self._export(namespace + "_q", record, check)
            if len(query_records) != 1 or query_records[0].get("document_id") != "query-anchor":
                raise EngineError("Query anchor must resolve to exactly one independently embedded text block")
            vector = sql_quote(vector_literal(query_records[0]["embedding"])) + "::vector"
        with timed_attempt(record, "pg_search", "query", "postgresql"):
            rows, sql, where = self._pg_search(namespace, path, vector, check)
        if self.pg_assist is not None and path in {"a1", "pg"}:
            if run_id is None or question is None:
                raise EngineError("PG assist requires run and question identity")
            self._emit(record, "pg_native_ranking", started, namespace=namespace, sql=sql, ranking=rows, ranking_scope="current_documents" if where else "all_documents")
            rows = self.pg_assist(run_id, path, question, [dict(row) for row in rows], record, check)
        with timed_attempt(record, "business_resolve", "query", "application"):
            resolver = resolve_candidates(rows, lifecycle=path != "a0")
        result = {"ranking": rows, "resolver": resolver, "selected_field": resolver["selected_field"], "query_kind": "application_hybrid_llm" if self.pg_assist is not None and path in {"a1", "pg"} else "native_pgvector_exact_cosine", "native_query_kind": "native_pgvector_exact_cosine", "ranking_scope": "current_documents" if where else "all_documents", "query_embedding_sha256": query_records[0]["embedding_sha256"]}
        self._emit(record, "pg_query_completed", started, namespace=namespace, sql=sql, **result)
        return result

    def _cortrix_query(self, namespace: str, files: list[dict[str, Any]], question: str, record: Record, check: Check) -> dict[str, Any]:
        started = time.monotonic()
        trace = {"session_id": namespace, "trace_id": uuid.uuid4().hex}
        locale = "zh" if re.search(r"[\u3400-\u9fff]", question) else "en"
        payload = {"query": question, "namespaces": [namespace], "top_k": 8, "rerank": True, "include_sources": True, "route": "complex", "crag": False, "granularity": "chunk", "explain": True, "search_config": {"enable_vector": True, "enable_bm25": True, "enable_sparse": True}, "rag_fusion": True, "rag_fusion_config": {"enabled": True, "variant_count": 3, "timeout_ms": 120000, "locale": locale, "candidate_multiplier": 5, "max_candidates": 40, "final_rerank": True, "activation_policy": "always"}, "llm_rerank": True, "llm_rerank_config": {"enabled": True, "top_n": 8, "timeout_ms": 120000, "locale": locale, "consensus_runs": 1}}
        check()
        before = self._metrics("full")
        self._emit(record, "cortrix_query_submitting", started, namespace=namespace, request=payload, trace_context=trace)
        with timed_attempt(record, "cortrix_search", "query", "cortrix"):
            check()
            _, response = self._http("full", "POST", "/query?explain=true", payload, timeout=360, trace=trace)
            self._emit(record, "cortrix_query_response", started, namespace=namespace, response=response, trace_context=trace)
        with timed_attempt(record, "evidence_verify", "query", "application"):
            check()
            after = self._metrics("full")
            durable = self._durable("full", namespace)
            by_doc = {d["doc_id"]: d["metadata"].get("document_id") for d in durable["documents"]}
            by_child = {b["child_id"]: by_doc.get(b["doc_id"]) for b in durable["text_blocks"]}
            fixtures = {f["document_id"]: f for f in files}
            if not isinstance(response, dict) or not isinstance(response.get("results"), list):
                raise EngineError("Cortrix query has no result list; inspect the RC2 response contract")
            meta = response.get("meta") or {}
            if response.get("error") or meta.get("namespaces_failed") != [] or meta.get("coverage_ratio") != 1 or namespace not in meta.get("namespaces_succeeded", []):
                raise EngineError("Cortrix returned an incomplete query response; inspect the preserved raw response")
            candidates = []
            for rank, item in enumerate(response["results"], 1):
                document_id = by_child.get(item.get("child_id"))
                if not document_id:
                    metadata = item.get("metadata") or {}
                    proposed = metadata.get("document_id") if isinstance(metadata, dict) else None
                    text = item.get("content") or item.get("parent_content") or ""
                    matches = [f["document_id"] for f in files if text and text in f["content"] and (not proposed or proposed == f["document_id"])]
                    document_id = matches[0] if len(matches) == 1 else None
                fixture = fixtures.get(document_id, {})
                candidates.append({**item, "rank": rank, "document_id": document_id, "lifecycle_status": fixture.get("status", "unknown"), "version": fixture.get("version", "unknown")})
            explain = response.get("explain") or {}
            dependent = explain.get("llm_dependent_features") or {}
            features = {name: (dependent.get(name) or {}).get("active") is True and (dependent.get(name) or {}).get("degraded") is not True for name in ("rag_fusion", "llm_rerank")}
            old, new = self._metric_values(before), self._metric_values(after)
            features["bge_reranker"] = new.get("cortrix_reranker_score_duration_seconds_count", 0) > old.get("cortrix_reranker_score_duration_seconds_count", 0)
            with timed_attempt(record, "business_resolve", "query", "application"):
                resolver = resolve_current_candidates(candidates)
            result = {"ranking": candidates, "resolver": resolver, "selected_field": resolver["selected_field"], "raw_response": response, "request": payload, "metrics_before": before, "metrics_after": after, "full_stack_checks": features, "full_stack_verified": all(features.values()), "ranking_scope": "returned_top_8_chunks", "policy_boundary": "Lifecycle selection is demo application policy over returned candidates; it is not an exhaustive full-corpus lifecycle query."}
            result["trace_context"] = trace
            self._emit(record, "cortrix_query_completed", started, namespace=namespace, **result)
            if not all(features.values()):
                raise EngineError("Cortrix query did not verify every requested Full Stack feature; inspect preserved evidence")
        return result

    def query(self, run_id: str, path: str, files: list[dict[str, Any]], question: str, record: Record, check: Check) -> dict[str, Any]:
        validate_files(files)
        namespace = namespace_for(run_id, path)
        check()
        arm = "full" if path == "b" else "embedding"
        if namespace in self.uncertain_namespaces or self.pending_tasks.get(namespace):
            raise ReconciliationRequired("Ingestion tasks must be reconciled before querying")
        durable = self._durable(arm, namespace)
        observed = {(d["metadata"].get("document_id"), d["metadata"].get("fixture_sha256")) for d in durable["documents"] if not d.get("deleted_at")}
        if observed != {(f["document_id"], f["sha256"]) for f in files}:
            raise ReconciliationRequired("Query inputs differ from the ingested immutable input set")
        if path != "b":
            check()
            anchors = self._durable(arm, namespace + "_q")["documents"]
            if len(anchors) != 1 or anchors[0]["metadata"].get("fixture_sha256") != content_hash(question):
                raise ReconciliationRequired("Question differs from the independently ingested query anchor")
        check()
        result = self._cortrix_query(namespace, files, question, record, check) if path == "b" else self._pg_query(namespace, path, record, check, run_id=run_id, question=question)
        return {"path": path, "namespace": namespace, **result}

    def snapshot(self, run_id: str, path: str) -> dict[str, Any]:
        namespace = namespace_for(run_id, path)
        arm = "full" if path == "b" else "embedding"
        status, api = self._http(arm, "GET", "/namespaces/" + namespace, expected={200, 404})
        result = {"path": path, "namespace": namespace, "namespace_http_status": status, "namespace_api": api, "durable": self._durable(arm, namespace), "runtime_identity": self.runtime_identity}
        if path != "b":
            result["postgres"] = self._pg_snapshot(namespace)
            result["query_anchor"] = self._durable(arm, namespace + "_q")
        return result

    def cleanup_exports(self, run_id: str, path: str) -> None:
        namespace = namespace_for(run_id, path)
        if path == "b":
            return
        for suffix in ("", "_q"):
            target = f"/data/{namespace}{suffix}_vectors.json"
            self._command(["docker", "exec", self.containers["embedding"], "python3", "-c",
                           "from pathlib import Path; import sys; Path(sys.argv[1]).unlink(missing_ok=True)", target])

    def cleanup(self, run_id: str, path: str, record: Record) -> dict[str, Any]:
        started = time.monotonic()
        namespace = namespace_for(run_id, path)
        arm = "full" if path == "b" else "embedding"
        before = self.snapshot(run_id, path)
        namespaces = [namespace] if path == "b" else [namespace, namespace + "_q"]
        for target in namespaces:
            if target in self.uncertain_namespaces:
                raise ReconciliationRequired("An upload outcome is unknown; reconcile its recorded submission before cleanup")
            for task_id in list(self.pending_tasks.get(target, set())):
                _, progress = self._http(arm, "GET", "/documents/tasks/" + urllib.parse.quote(task_id, safe="") + "/progress")
                if str(progress.get("status", "")).lower() not in SUCCESS | FAILURE:
                    raise ReconciliationRequired("An accepted document task is still running")
                self.pending_tasks[target].discard(task_id)
            durable = self._durable(arm, target)
            if any(str(d.get("status", "")).lower() not in SUCCESS | FAILURE | {"active", "indexed", "deleted"} for d in durable["documents"]):
                raise ReconciliationRequired("Namespace still has unresolved document state; stop and reconcile tasks before cleanup")
            if any(s["status"] not in {"ok", "failed", "failed_permanent", "cancelled", "canceled"} for s in durable["enrich_states"]):
                raise ReconciliationRequired("Namespace still has unresolved enrichment work")
            status, response = self._http(arm, "DELETE", "/namespaces/" + target, expected={204, 404})
            verify, _ = self._http(arm, "GET", "/namespaces/" + target, expected={200, 404})
            after_durable = self._durable(arm, target)
            self._emit(record, "namespace_cleanup_receipt", started, namespace=target, http_status=status, response=response, verification_http_status=verify, durable=after_durable)
            if verify != 404 or after_durable["documents"] or after_durable["text_blocks"]:
                raise ReconciliationRequired("Namespace API or durable data still exists after deletion; inspect the RC2 cleanup contract")
        if path != "b":
            self._sql(f"DROP SCHEMA IF EXISTS {schema_name(namespace)} CASCADE;")
            if self._pg_snapshot(namespace)["exists"]:
                raise EngineError("PostgreSQL schema still exists after cleanup")
        result = {"path": path, "namespace": namespace, "before": before, "namespaces_removed": True, "postgres_removed": path != "b", "original_files_preserved": True, "services_preserved": True, "export_files": [f"/data/{target}_vectors.json" for target in namespaces] if path != "b" else [], "export_files_retained_for_evidence_cleanup": path != "b"}
        self._emit(record, "cleanup_completed", started, **result)
        return result
