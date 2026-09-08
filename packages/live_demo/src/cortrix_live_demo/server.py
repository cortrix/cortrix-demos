"""Authenticated local demo controller with real engines and durable evidence."""
from __future__ import annotations

import argparse
import base64
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from .fixtures import seed, question, QUESTION_CONTRACT
from .state import State, Paused, atomic, stamp, digest, RUN_LIMITS, EXECUTION_CONTRACT
from .operation_timing import safe_error_message, timed_attempt
from .config import RuntimeConfig, load_config, load_provider_secret, CORTRIX_COMMIT, PACKAGE_ROOT

ROOT = Path(__file__).resolve().parent
VIEWER_ROOT = PACKAGE_ROOT / "viewer"


class Controller:
    def __init__(self, root, engine=None, seed_inputs=True, config: RuntimeConfig | None = None):
        self.config = config or load_config()
        self.state = State(root, self.config)
        self.engine = engine
        self.active = None
        self.worker = None
        self.engine_lock = threading.RLock()
        self.csrf = secrets.token_urlsafe(24)
        self.internal = secrets.token_urlsafe(32)
        self.context = None
        self.key = None
        self.runtime_manager = None
        atomic(Path(root) / "access.json", {"access_mode": "loopback_operator", "csrf": self.csrf, "internal": self.internal})
        if seed_inputs:
            seed(self.state, self.config.fixtures_root)
        with self.state.lock:
            for item in list(self.state.data["runs"]):
                if item["state"] in {"running", "queued", "cancelling", "cleaning"}:
                    run = self.state.get(item["id"])
                    self.reconcile_interrupted_timing(run)
                    run = self.state.get(item["id"])
                    run.update(state="interrupted", error="Service restarted; reconcile unfinished operations before continuing")
                    self.state.put(run)

    def reconcile_interrupted_timing(self, run):
        """Close only new-schema open attempts without inventing an end clock."""
        started, ended = {}, set()
        for event in run.get("events", []):
            artifact = self.state.run_path(run["id"]) / event["artifact_ref"]
            value = json.loads(artifact.read_text())
            attempt_id = value.get("attempt_id")
            if value.get("schema_version") != 2 or not attempt_id:
                continue
            if event["stage"].endswith("_started"):
                started[attempt_id] = (event, value)
            else:
                ended.add(attempt_id)
        for attempt_id, (event, value) in started.items():
            if attempt_id in ended:
                continue
            terminal = {key: value[key] for key in
                        ("schema_version", "attempt_id", "parent_attempt_id", "process_instance_id",
                         "step_id", "operation", "owner", "source", "timing_scope", "started_monotonic_ns")
                        if key in value}
            terminal.update(state="interrupted", status="interrupted", duration_ms=None,
                            error="The prior process ended without a terminal timing receipt")
            self.state.event(run["id"], event["path"], event["stage"].removesuffix("_started") + "_interrupted", terminal)

    def workspace(self):
        with self.state.lock:
            return {"files": self.state.data["files"], "runs": self.state.data["runs"],
                    "current_run_id": self.state.data["current_run_id"], "budget": self.state.budget(),
                    "question": question(self.config.fixtures_root), "question_contract": QUESTION_CONTRACT,
                    "locale": "en-US", "access_mode": "loopback_operator",
                    "limits": {"files": 8, "per_file_bytes": 2097152, "total_bytes": 8388608},
                    "run_allowance": self.state.run_allowance(),
                    "runtime_ready": self.engine is not None}

    def update(self, rid, **changes):
        with self.state.lock:
            run = self.state.get(rid)
            run.update(changes)
            self.state.put(run)

    def path_update(self, rid, path, **changes):
        with self.state.lock:
            run = self.state.get(rid)
            run["paths"][path].update(changes)
            self.state.put(run)

    def check(self, rid):
        run = self.state.get(rid)
        if run["cancel_requested"]:
            raise Paused("DEMO_CANCELLED")
        if run["state"] != "running":
            raise Paused(run.get("error") or "DEMO_RUN_NOT_RUNNING")

    def restore_tasks(self, rid):
        if not hasattr(self.engine, "restore_pending_tasks"):
            return
        pending = {}
        uncertain = set()
        for event in self.state.get(rid)["events"]:
            if event["stage"] not in {"document_submitting", "document_task_accepted", "document_task_progress", "document_task_reconciled", "document_written"}:
                continue
            value = json.loads((self.state.run_path(rid) / event["artifact_ref"]).read_text())
            ns = value.get("namespace")
            response = value.get("response") or {}
            task_id = value.get("task_id") or response.get("task_id")
            if event["stage"] == "document_submitting":
                uncertain.add(ns)
            if event["stage"] == "document_task_accepted" and task_id:
                uncertain.discard(ns)
                pending[task_id] = ns
            if task_id and (event["stage"] == "document_written" or str(response.get("status", "")).lower() in {"completed", "ready", "success", "succeeded", "failed", "cancelled", "error"}):
                pending.pop(task_id, None)
        for ns in {v for v in pending.values()}:
            self.engine.restore_pending_tasks(ns, [k for k,v in pending.items() if v == ns])
        self.engine.uncertain_namespaces.update(ns for ns in uncertain if ns)
        if uncertain:
            raise Paused("DEMO_UPLOAD_OUTCOME_UNRESOLVED")

    def create(self, payload):
        if self.engine is None:
            raise ValueError("RC2 runtime has not passed preflight")
        run, fresh = self.state.create(payload)
        if fresh:
            run["code_manifest"] = self.code_manifest()
            run["execution_contract"] = EXECUTION_CONTRACT
            run["timing_schema_version"] = 2
            run["pg_llm_assist_profile"] = {"version": "pg_hybrid_llm_v1", "paths": ["a1"] if run["mode"] == "deterministic" else ["pg"], "model": "deepseek-v4-flash", "max_requests_per_path": 1, "features": ["query_expansion", "pg_lexical_retrieval", "reciprocal_rank_fusion", "llm_rerank"]}
            from .code_inventory import inventory
            current_inventory = inventory(config=self.config)
            run["code_inventory_snapshot"] = {key: current_inventory[key] for key in ("counts", "source_manifest_sha256", "inventory_implementation_sha256")}
            run["question_contract"] = QUESTION_CONTRACT if run["question"] == question(self.config.fixtures_root) else "operator_custom_question"
            run["question_sha256"] = digest(run["question"].encode())
            run["runtime_identity"] = dict(getattr(self.engine, "runtime_identity", {}))
            self.state.put(run)
            self.start(run["id"])
        return run

    def code_manifest(self):
        sources = list(ROOT.glob("*.py"))
        sources += list((PACKAGE_ROOT / "harness").glob("*.mjs"))
        manifest = {p.relative_to(PACKAGE_ROOT).as_posix(): digest(p.read_bytes()) for p in sorted(sources)}
        configured = {
            "runtime-support/helpers/extract_vectors.py": self.config.helpers_root / "extract_vectors.py",
            "runtime-support/config/cortrix.embedding-only.yaml": self.config.configs_root / "cortrix.embedding-only.yaml",
            "runtime-support/config/cortrix.full-stack.yaml": self.config.configs_root / "cortrix.full-stack.yaml",
        }
        for label, path in configured.items():
            manifest[label] = digest(path.read_bytes())
        identity = self.config.execution_identity()
        manifest["runtime-config"] = digest(json.dumps(identity, sort_keys=True).encode())
        return manifest

    def start(self, rid):
        with self.state.lock:
            if self.worker is not None and self.worker.is_alive():
                raise ValueError("Another worker is active")
            if self.engine is None:
                raise ValueError("RC2 runtime is unavailable")
            run = self.state.get(rid)
            if run.get("code_manifest") and run["code_manifest"] != self.code_manifest():
                raise Paused("DEMO_CODE_CHANGED: review the changed execution identity before resuming")
            if run["state"] in {"cleaned", "completed", "cleaning"}:
                raise ValueError("This run cannot be resumed")
            if any(r["run_id"] == rid and r["state"] != "completed" for r in self.state.data["requests"]):
                raise Paused("DEMO_UNRESOLVED_REQUEST: reconcile the provider receipt first")
            self.active = rid
            self.restore_tasks(rid)
            self.update(rid, state="running", cancel_requested=False, error=None)
            self.worker = threading.Thread(target=self.execute, args=(rid,), daemon=True)
            self.worker.start()

    def execute(self, rid):
        try:
            run = self.state.get(rid)
            for path in run["paths"]:
                if self.state.get(rid)["paths"][path]["state"] == "completed":
                    continue
                self.check(rid)
                self.context = {"run_id": rid, "path": path}
                self.path_update(rid, path, state="running")
                if self.runtime_manager is not None:
                    def runtime_record(stage, value):
                        name = "runtime_prepared" if stage == "runtime_completed" else stage
                        self.state.event(rid, path, name, {**value, "component": "full" if path == "b" else "embedding",
                                                          "stage_total_includes_setup": False})
                    with timed_attempt(runtime_record, "runtime_activation", "setup", "application",
                                       source="runtime_control", event_prefix="runtime", timing_scope="setup"):
                        if path == "b":
                            self.runtime_manager.bind_run(rid, self.internal)
                        else:
                            self.runtime_manager.activate_component("embedding")
                if run["mode"] == "harness":
                    record = lambda stage, value: self.state.event(rid, path, stage, value)
                    with timed_attempt(record, "harness_execution", "agent", "application", source="controller", event_prefix="harness", timing_scope="agent") as attempt:
                        self.context.update(operation="agent", parent_attempt_id=attempt["attempt_id"], process_instance_id=attempt["process_instance_id"])
                        self.run_harness(rid, path)
                else:
                    self.operation(rid, path, "ingest", {})
                    result = self.operation(rid, path, "query", {})
                    self.path_update(rid, path, state="completed", result=result)
            self.check(rid)
            if any(i["run_id"] == rid and i["state"] != "completed" for i in self.state.data["requests"]):
                raise Paused("DEMO_USAGE_UNRESOLVED")
            self.update(rid, state="completed", completed_at=stamp())
        except Exception as exc:
            current = self.state.get(rid)
            raw_message = str(exc)
            message = safe_error_message(exc)
            if current["state"] == "needs_reconciliation":
                status = "needs_reconciliation"
                message = current.get("error") or message
            elif current["state"] == "paused_budget" or "BUDGET" in raw_message or "TURN_LIMIT" in raw_message:
                status = "paused_budget"
            elif "UNRESOLVED" in raw_message:
                status = "needs_reconciliation"
            elif "CANCELLED" in raw_message:
                status = "cancelled"
            else:
                status = "failed"
            for failed_path, value in current["paths"].items():
                if value["state"] == "running":
                    self.path_update(rid, failed_path, state=status)
            self.update(rid, state=status, error=message[:600])
        finally:
            self.context = None
            self.active = None

    def operation(self, rid, path, operation, arguments):
        if rid != self.active:
            raise ValueError("Tool call does not belong to the active run")
        with self.engine_lock:
            run = self.state.get(rid)
            if path not in run["paths"]:
                raise ValueError("Unknown path")
            self.check(rid)
            previous_context = dict(self.context or {"run_id": rid, "path": path})
            checkpoint = run["paths"][path]["checkpoint"]
            if operation in checkpoint:
                return checkpoint[operation]
            if operation == "status":
                return self.engine.snapshot(rid, path)
            if operation not in {"ingest", "query"}:
                raise ValueError("Unknown operation")
            if operation == "query" and "ingest" not in checkpoint:
                raise ValueError("Ingest must finish before querying")
            if arguments.get("input_ids") and sorted(arguments["input_ids"]) != sorted(f["id"] for f in run["files"]):
                raise ValueError("Tool input must match the frozen corpus")
            question = arguments.get("query", run["question"])
            if question != run["question"]:
                raise ValueError("The paired experiment requires the frozen question")
            outcome = {}
            def record(stage, value):
                if value.get("timing_scope") == "operation" and not value.get("parent_attempt_id"):
                    value = {**value, "parent_attempt_id": previous_context.get("parent_attempt_id")}
                if stage == operation + "_completed" and value.get("source") == "controller":
                    value = {**value, **outcome}
                return self.state.event(rid, path, stage, value)
            try:
                with timed_attempt(record, operation, operation, "application",
                                   source="controller", event_prefix=operation, timing_scope="operation") as attempt:
                    self.context = {"run_id": rid, "path": path, "operation": operation,
                                    "parent_attempt_id": attempt["attempt_id"],
                                    "process_instance_id": attempt["process_instance_id"]}
                    if hasattr(self.engine, "pg_assist"):
                        enabled = path in run.get("pg_llm_assist_profile", {}).get("paths", [])
                        self.engine.pg_assist = self.pg_assist if enabled else None
                    fn = getattr(self.engine, operation)
                    result = fn(rid, path, run["files"], question, record, lambda: self.check(rid))
                    outcome["result"] = result
            finally:
                self.context = previous_context
            with self.state.lock:
                current = self.state.get(rid)
                current["paths"][path]["checkpoint"][operation] = result
                if operation == "query":
                    current["paths"][path]["result"] = result
                self.state.put(current)
            return result

    def application_model_call(self, rid, path, task, payload):
        """Reserve, persist, and settle one bounded application model request."""
        from .operation_timing import current_timing_context
        self.check(rid)
        run = self.state.get(rid)
        if self.active != rid or not self.context or self.context.get("path") != path:
            raise PermissionError("Application model request is outside the active execution")
        if path not in run.get("pg_llm_assist_profile", {}).get("paths", []) or task != "query_plan_rerank":
            raise PermissionError("Application model task is outside the frozen profile")
        if payload.get("stream") is not False or payload.get("response_format") != {"type": "json_object"}:
            raise ValueError("Application model tasks require bounded nonstreaming JSON output")
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        payload_hash = digest(body)
        request_id = "application_" + digest((rid + ":" + path + ":" + task).encode())[:32]
        existing = next((item for item in self.state.data["requests"] if item["request_id"] == request_id), None)
        if existing is not None:
            if existing.get("payload_sha256") != payload_hash:
                raise Paused("DEMO_APPLICATION_MODEL_INPUT_CHANGED")
            if existing["state"] != "completed":
                raise Paused("DEMO_APPLICATION_MODEL_OUTCOME_UNRESOLVED")
            for event in reversed(run["events"]):
                if event["stage"] != "application_model_response":
                    continue
                receipt = json.loads((self.state.run_path(rid) / event["artifact_ref"]).read_text())
                if receipt.get("request_id") == request_id and receipt.get("payload_sha256") == payload_hash:
                    return receipt["response"]
            raise Paused("DEMO_APPLICATION_MODEL_RECEIPT_UNRESOLVED")
        harness = run["mode"] == "harness"
        session_id = None
        if harness:
            sessions = {item.get("session_id") for item in self.state.data["requests"]
                        if item["run_id"] == rid and item["path"] == path and item.get("harness")
                        and item.get("origin") != "application_llm" and item.get("session_id")}
            if len(sessions) != 1:
                raise Paused("DEMO_APPLICATION_NATIVE_SESSION_UNRESOLVED")
            session_id = sessions.pop()
        try:
            self.state.reserve(rid, path, request_id, payload, harness, session_id, origin="application_llm",
                               task=task, payload_sha256=payload_hash)
        except Paused as exc:
            self.update(rid, state="paused_budget", error=str(exc))
            raise
        context = current_timing_context()
        event_data = {"source": "application_llm", "operation": "query", "request_id": request_id,
                      "task": task, "payload_sha256": payload_hash, "request": payload,
                      "session_id": session_id, "harness": harness, **context}
        self.state.event(rid, path, "application_model_request", event_data)
        started = time.monotonic_ns()
        try:
            request = urllib.request.Request(self.config.provider_base_url + "/chat/completions", data=body,
                                             headers={"Content-Type": "application/json",
                                                      "Authorization": "Bearer " + self.secret()})
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = response.read()
            value = json.loads(raw)
            usage = value.get("usage")
            self.state.event(rid, path, "application_model_response",
                             {**event_data, "response": value, "usage": usage,
                              "duration_ms": (time.monotonic_ns() - started) / 1e6})
            self.state.settle(request_id, usage)
            return value
        except Paused as exc:
            self.update(rid, state="needs_reconciliation", error=str(exc))
            raise
        except Exception:
            self.update(rid, state="needs_reconciliation",
                        error="Application model outcome unknown; reconcile the retained reservation before resuming")
            raise

    def pg_assist(self, rid, path, question, vector_candidates, record, check):
        from .engines import namespace_for, schema_name, sql_quote
        from .llm_assist import augment
        run = self.state.get(rid)
        if run.get("execution_contract") != EXECUTION_CONTRACT or path not in run.get("pg_llm_assist_profile", {}).get("paths", []):
            raise PermissionError("Application assistance requires the frozen new execution profile")
        table = schema_name(namespace_for(rid, path))
        def lexical_search(query):
            query_sql = sql_quote(query)
            sql = (
                "SELECT coalesce(json_agg(row_to_json(r)), '[]'::json) FROM ("
                "SELECT block_id,document_id,chunk_index,version,lifecycle_status,content,"
                f"ts_rank_cd(to_tsvector('simple',content),plainto_tsquery('simple',{query_sql})) AS lexical_score "
                f"FROM {table}.semantic_blocks WHERE lifecycle_status='current' "
                f"AND to_tsvector('simple',content) @@ plainto_tsquery('simple',{query_sql}) "
                "ORDER BY lexical_score DESC,document_id,chunk_index LIMIT 8) r;"
            )
            rows = self.engine._sql_json(sql)
            record("pg_lexical_candidates", {"source": "application_llm", "operation": "query",
                                              "query": query, "sql": sql, "ranking": rows})
            return rows
        return augment(question, vector_candidates,
                       lambda task, payload: self.application_model_call(rid, path, task, payload),
                       lexical_search, record, check)

    def run_harness(self, rid, path):
        run = self.state.get(rid)
        environment = os.environ.copy()
        environment.update(DEMO_BASE_URL=self.config.operator_origin, DEMO_INTERNAL_TOKEN=self.internal,
                           DEMO_RUN_ID=rid, DEMO_PATH=path,
                           DEMO_INPUT_IDS=json.dumps([f["id"] for f in run["files"]]),
                           DEMO_QUESTION=run["question"], DEMO_SESSION_ROOT=str(self.state.root / "harness"),
                           DEMO_HARNESS_ROOT=str(self.config.harness_root),
                           DEMO_HARNESS_COMMIT=self.config.harness_commit)
        receipt = self.state.root / "harness" / rid / path / "receipt.json"
        driver_state = receipt.parent / "driver-state.json"
        schemas = {receipt: "cortrix_live_demo_harness_receipt/v1", driver_state: "cortrix_live_demo_harness_state/v1"}
        for artifact, schema in schemas.items():
            if artifact.exists():
                previous = json.loads(artifact.read_text())
                if previous.get("schema") != schema or previous.get("adapter_version") != "cortrix_live_demo_harness_v1":
                    raise Paused("DEMO_HARNESS_ADAPTER_VERSION_MISMATCH: preserve the existing session with its original adapter")
        if receipt.exists():
            previous = json.loads(receipt.read_text())
            if previous.get("session_id"):
                environment["DEMO_RESUME_SESSION_ID"] = previous["session_id"]
        if driver_state.exists() and "DEMO_RESUME_SESSION_ID" not in environment:
            environment["DEMO_RESUME_SESSION_ID"] = json.loads(driver_state.read_text())["session_id"]
        result = subprocess.run(["node", str(PACKAGE_ROOT / "harness" / "launch.mjs")], env=environment,
                                capture_output=True, text=True, timeout=1800)
        if result.returncode:
            raise RuntimeError("Harness did not complete; preserve its runtime receipt without replaying it into this run")
        if not receipt.exists():
            raise RuntimeError("Harness did not produce a durable receipt; inspect the local runtime logs")
        value = json.loads(receipt.read_text())
        if value.get("schema") != "cortrix_live_demo_harness_receipt/v1" or value.get("adapter_version") != "cortrix_live_demo_harness_v1" or value.get("run_id") != rid or value.get("path") != path:
            raise Paused("DEMO_HARNESS_RECEIPT_IDENTITY_MISMATCH")
        self.state.event(rid, path, "harness_receipt", {"source": "deepseek_harness", **value})
        if not self.state.get(rid)["paths"][path]["checkpoint"].get("query"):
            raise RuntimeError("Harness stopped before real ingestion and query both completed")
        query_result = self.state.get(rid)["paths"][path]["checkpoint"]["query"]
        projection = self.tool_projection(rid, path, "query", query_result)
        from .answer_contract import validate_answer
        validation = validate_answer(value.get("final_response", ""), projection, query_result["resolver"])
        value.update(validation)
        decision = validation["decision"]
        self.state.event(rid, path, "harness_business_validation", {"source": "independent_application_validation", **validation})
        query_result = {**query_result, "engine_selected_field": query_result["selected_field"],
                        "selected_field": decision["selected_field"] if validation["business_verdict"] == "pass" else "unknown",
                        "agent_decision": decision, "business_verdict": value["business_verdict"]}
        self.path_update(rid, path, result=query_result)
        self.path_update(rid, path, state="completed", harness=value)

    def tool_projection(self, rid, path, operation, value):
        run = self.state.get(rid)
        artifact = next((e["artifact_ref"] for e in reversed(run["events"]) if e["path"] == path and e["stage"] == operation + "_completed"), None)
        if operation == "ingest":
            original = value.get("result") or {}
            return {"operation": operation, "status": "ready", "document_count": value["document_count"],
                    "original_chunk_count": len(original.get("text_blocks", [])) if path == "b" else original.get("row_count"),
                    "input_manifest_sha256": digest(json.dumps(sorted((f["document_id"], f["sha256"]) for f in run["files"])).encode()),
                    "artifact_ref": artifact}
        if operation == "status":
            durable = value.get("durable") or {}
            return {"operation": operation, "namespace": value["namespace"], "document_count": len(durable.get("documents", [])),
                    "original_chunk_count": len(durable.get("text_blocks", [])), "artifact_ref": artifact}
        evidence = []
        for item in value["ranking"][:8]:
            content = str(item.get("content") or item.get("parent_content") or "")
            raw = content.encode()
            evidence.append({"rank": item["rank"], "evidence_ref": f"{rid}:{path}:{item['rank']}:{item.get('document_id')}",
                             "document_id": item.get("document_id"), "version": item.get("version"),
                             "lifecycle_status": item.get("lifecycle_status", "unknown"),
                             "content": raw[:2048].decode("utf-8", errors="ignore"), "content_truncated": len(raw) > 2048})
        return {"operation": operation, "status": "ok", "returned_count": len(evidence), "limit": 8,
                "truncated": len(value["ranking"]) > 8 or any(e["content_truncated"] for e in evidence),
                "evidence": evidence, "artifact_ref": artifact}

    def cancel(self, rid):
        run = self.state.get(rid)
        if run["state"] in {"completed", "cleaned"}:
            return run
        self.update(rid, cancel_requested=True, state="cancelling" if self.active == rid else "cancelled")
        return self.state.get(rid)

    def cleanup(self, rid):
        with self.state.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError("Stop and reconcile the active run before cleanup")
            run = self.state.get(rid)
            if run["state"] == "cleaned":
                return run
            if run["state"] == "cleaning":
                raise ValueError("Cleanup is already in progress")
            self.restore_tasks(rid)
            self.update(rid, state="cleaning", cancel_requested=True)
        self.engine_lock.acquire()
        try:
            receipts = []
            originals_before = {f["id"]: digest((self.state.root / "originals" / (f["id"] + ".json")).read_bytes()) for f in run["files"]}
            for path in run["paths"]:
                if self.runtime_manager is not None:
                    self.runtime_manager.activate_component("full" if path == "b" else "embedding")
                detailed = self.engine.cleanup(rid, path, lambda stage,value: self.state.event(rid,path,stage,value))
                receipts.append({k:detailed[k] for k in ("path", "namespace", "namespaces_removed", "postgres_removed", "original_files_preserved", "services_preserved") if k in detailed})
                if hasattr(self.engine, "cleanup_exports"):
                    self.engine.cleanup_exports(rid, path)
            folder = self.state.run_path(rid)
            original_ids = [f["id"] for f in run["files"]]
            # Only generated artifacts from this validated run are removed.
            for generated in (folder / "artifacts").glob("*.json"):
                generated.unlink()
            harness_root = self.state.root / "harness" / rid
            if harness_root.exists():
                for generated in sorted(harness_root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                    if generated.is_symlink():
                        raise ValueError("Unexpected symlink in generated data")
                    if generated.is_file():
                        generated.unlink()
                    elif generated.is_dir():
                        generated.rmdir()
            receipt = {"run_id": rid, "completed_at": stamp(), "generated_objects": receipts,
                       "original_ids_preserved": original_ids, "budget_preserved": True}
            if any(digest((self.state.root / "originals" / (fid + ".json")).read_bytes()) != sha for fid,sha in originals_before.items()):
                raise ValueError("An original changed during cleanup")
            receipt["original_integrity_verified"] = True
            atomic(folder / "cleanup-receipt.json", receipt)
            self.update(rid, state="cleaned", events=[], paths={}, files=[], input_ids=original_ids,
                        cleanup=receipt, question="", error=None)
        except Exception:
            self.update(rid, state="cleanup_failed")
            raise
        finally:
            self.engine_lock.release()
        return self.state.get(rid)

    def secret(self):
        if self.key is None:
            self.key = load_provider_secret(self.config)
        return self.key


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    @property
    def ctl(self):
        return self.server.controller

    @property
    def surface(self):
        return getattr(self.server, "surface", "operator")

    def respond(self, value, status=200, content_type="application/json; charset=utf-8"):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 12 * 1024 * 1024:
            raise ValueError("Request is too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def auth(self, internal=False, write=False):
        if internal:
            header = self.headers.get("Authorization", "")
            candidate = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
            if not secrets.compare_digest(candidate, self.ctl.internal):
                raise PermissionError("Internal service authentication required")
        if write and not internal:
            if self.headers.get("Origin") != self.ctl.config.operator_origin or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), self.ctl.csrf):
                raise PermissionError("Invalid origin or CSRF token")

    def require_operator_host(self):
        expected = urllib.parse.urlsplit(self.ctl.config.operator_origin).netloc
        if self.headers.get("Host", "") != expected:
            raise PermissionError("Operator Host does not match the configured origin")

    def do_GET(self):
        try:
            target = urllib.parse.urlsplit(self.path)
            path = target.path
            if self.surface == "internal":
                if path == "/healthz":
                    return self.respond({"state": "ready" if self.ctl.engine else "locked", "version": 1})
                return self.respond({"error": "Not found"}, 404)
            self.require_operator_host()
            # Keep result bookmarks stable while making the overview the default entry.
            if path == "/demo/" or (
                path in {"/", "/index.html"}
                and "run" in urllib.parse.parse_qs(target.query, keep_blank_values=True)
            ):
                location = "/demo" + ("?" + target.query if target.query else "")
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if path in {"/", "/index.html"}:
                file = VIEWER_ROOT / "intro.html"
                return self.respond(file.read_bytes(), content_type="text/html; charset=utf-8")
            if path == "/demo":
                return self.respond((VIEWER_ROOT / "index.html").read_bytes(), content_type="text/html; charset=utf-8")
            if path == "/healthz":
                return self.respond({"state": "ready" if self.ctl.engine else "locked", "version": 1})
            if path == "/api/session":
                if self.headers.get("Origin") not in {None, self.ctl.config.operator_origin} or self.headers.get("Sec-Fetch-Site") in {"cross-site", "same-site"}:
                    raise PermissionError("Same-origin page context required")
                return self.respond({"csrf": self.ctl.csrf, "access_mode": "loopback_operator"})
            if path in {"/app.js", "/api.js", "/styles.css", "/evidence.html", "/evidence.js"} or path.startswith("/assets/"):
                file = (VIEWER_ROOT / path.lstrip("/")).resolve()
                if not file.is_relative_to(VIEWER_ROOT.resolve()) or not file.is_file():
                    return self.respond({"error": "Not found"}, 404)
                return self.respond(file.read_bytes(), content_type=mimetypes.guess_type(str(file))[0] or "application/octet-stream")
            self.auth()
            if path == "/api/workspace":
                return self.respond(self.ctl.workspace())
            if path == "/api/code":
                from .code_inventory import inventory
                return self.respond(inventory(config=self.ctl.config))
            m = re.fullmatch(r"/api/runs/(run_[0-9a-f]{16})(/evidence|/events)?", path)
            if m:
                run = self.ctl.state.get(m[1])
                from .event_projection import details
                projected = {}
                for event in run["events"]:
                    artifact = (self.ctl.state.run_path(run["id"]) / event["artifact_ref"]).resolve()
                    if not artifact.is_relative_to(self.ctl.state.run_path(run["id"]).resolve()):
                        raise ValueError("Event artifact is outside this run")
                    raw = json.loads(artifact.read_text())
                    event["original_event_state"] = event["state"]
                    event.update(details(event["stage"], raw))
                    projected[event["sequence"]] = event
                for path_data in run["paths"].values():
                    path_data["steps"] = [projected.get(e["sequence"], e) for e in path_data["steps"]]
                if run["mode"] == "harness":
                    from .answer_normalization import normalize_answer
                    for path_id, path_data in run["paths"].items():
                        if path_data.get("harness") and path_data.get("checkpoint", {}).get("query"):
                            path_data["normalized_answer"] = normalize_answer(path_data["harness"]["final_response"], run["id"], path_id, path_data["checkpoint"]["query"])
                if m[2] == "/evidence":
                    artifacts = [{"name": f.name, "content": json.loads(f.read_text())} for f in sorted((self.ctl.state.run_path(m[1]) / "artifacts").glob("*.json"))]
                    return self.respond({"schema": "cortrix_live_demo_run_evidence/v1",
                                         "manifest": {k:v for k,v in run.items() if k not in {"files"}},
                                         "artifacts": artifacts})
                if m[2] == "/events":
                    last = self.headers.get("Last-Event-ID", "0").split(":")[-1]
                    after = int(last) if last.isdigit() else 0
                    data = "".join(f"id: {run['id']}:{e['sequence']}\ndata: {json.dumps(e,ensure_ascii=False)}\n\n" for e in run["events"] if e["sequence"] > after).encode()
                    return self.respond(data, content_type="text/event-stream")
                return self.respond(run)
            self.respond({"error": "Not found"}, 404)
        except PermissionError as exc:
            self.respond({"error": str(exc)}, 401)
        except Exception as exc:
            self.respond({"error": "Request failed", "code": type(exc).__name__}, 400)

    def do_POST(self):
        try:
            path = urllib.parse.urlsplit(self.path).path
            if self.surface == "operator":
                self.require_operator_host()
            core = re.fullmatch(r"/internal/core/(run_[0-9a-f]{16})/model/v1/chat/completions", path)
            if self.surface == "internal" and path not in {"/internal/model/v1/chat/completions", "/internal/harness/tool"} and not core:
                return self.respond({"error": "Not found"}, 404)
            if path == "/internal/model/v1/chat/completions" or core:
                self.auth(internal=True)
                return self.proxy(self.body(), core_run_id=core[1] if core else None)
            if path == "/internal/harness/tool":
                self.auth(internal=True)
                payload = self.body()
                result = self.ctl.operation(payload["run_id"], payload["path"], payload["operation"], payload.get("arguments", {}))
                return self.respond(self.ctl.tool_projection(payload["run_id"], payload["path"], payload["operation"], result))
            self.auth(write=True)
            payload = self.body()
            if path == "/api/files":
                raw = base64.b64decode(payload["content_base64"], validate=True)
                return self.respond(self.ctl.state.add_file(payload["name"], raw), 201)
            if path == "/api/runs":
                return self.respond(self.ctl.create(payload), 202)
            match = re.fullmatch(r"/api/runs/(run_[0-9a-f]{16})/(cancel|resume|cleanup)", path)
            if match:
                rid, action = match.groups()
                if action == "resume":
                    self.ctl.start(rid)
                    return self.respond(self.ctl.state.get(rid), 202)
                return self.respond(getattr(self.ctl, action)(rid))
            self.respond({"error": "Not found"}, 404)
        except PermissionError as exc:
            self.respond({"error": str(exc)}, 401)
        except Paused as exc:
            self.respond({"error": {"code": str(exc).split(":")[0], "message": str(exc)}}, 409)
        except Exception as exc:
            self.respond({"error": "Request failed", "code": type(exc).__name__}, 400)

    def proxy(self, payload, core_run_id=None):
        context = self.ctl.context
        if not context:
            raise Paused("DEMO_NO_ACTIVE_RUN")
        harness = core_run_id is None
        rid = self.headers.get("X-Demo-Run-Id") if harness else core_run_id
        path = self.headers.get("X-Demo-Path") if harness else "b"
        if harness and not all(self.headers.get(key) for key in ("X-Demo-Run-Id", "X-Demo-Path", "X-Demo-Session-Id", "X-Demo-Request-Id")):
            raise PermissionError("Harness request attribution is required")
        if rid != self.ctl.active or path != context["path"]:
            raise PermissionError("Model request is outside the active execution")
        request_id = self.headers.get("X-Demo-Request-Id", "provider_" + uuid.uuid4().hex)
        payload.setdefault("max_tokens", 2048)
        try:
            self.ctl.state.reserve(rid, path, request_id, payload, harness, self.headers.get("X-Demo-Session-Id"))
        except Paused as exc:
            self.ctl.update(rid, state="paused_budget", error=str(exc))
            raise
        start = time.monotonic_ns()
        timing = {key: context.get(key) for key in ("operation", "parent_attempt_id", "process_instance_id")}
        if harness:
            timing["operation"] = "agent"
        timing["timing_scope"] = "provider_request"
        self.ctl.state.event(rid, path, "provider_request", {"source": "provider_proxy", "request_id": request_id, **timing, "state": "started",
                                                          "payload_sha256": digest(json.dumps(payload,sort_keys=True).encode()),
                                                          "stream": payload.get("stream", False)})
        req = urllib.request.Request(self.ctl.config.provider_base_url + "/chat/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.ctl.secret()})
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                if payload.get("stream"):
                    usage = None
                    chunks = []
                    for line in response:
                        chunks.append(line.decode("utf-8"))
                        if line.startswith(b"data: ") and not line.startswith(b"data: [DONE]"):
                            value = json.loads(line[6:])
                            usage = value.get("usage") or usage
                    response_body = {"sse": chunks}
                    raw = "".join(chunks).encode()
                else:
                    raw = response.read()
                    response_body = json.loads(raw)
                    usage = response_body.get("usage")
                self.ctl.state.event(rid, path, "provider_response", {"source": "deepseek", "request_id": request_id, **timing,
                                                                   "duration_ms": (time.monotonic_ns()-start)/1e6,
                                                                   "usage": usage, "response": response_body})
                self.ctl.state.settle(request_id, usage)
                # Forward authentic provider bytes only after usage is durably settled.
                self.respond(raw, content_type="text/event-stream" if payload.get("stream") else "application/json")
        except Paused as exc:
            self.ctl.update(rid, state="needs_reconciliation", error=str(exc))
            raise
        except Exception:
            # Unknown provider outcomes retain their reservation and are never retried.
            self.ctl.update(rid, state="failed", error="Provider outcome unknown; reconcile the reserved request before resuming")
            raise


def _acquire_runtime_lock(runtime: Path) -> int:
    """Lock an initialized runtime directory without creating a lock artifact."""
    if not runtime.is_dir():
        raise ValueError("The runtime directory must exist before the service starts")
    descriptor = os.open(runtime, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise RuntimeError("Another service already owns this runtime directory") from exc
    return descriptor


def serve(config: RuntimeConfig, *, locked: bool = False) -> None:
    """Serve the operator and internal surfaces until interrupted."""
    runtime = config.runtime_root
    lock_descriptor = _acquire_runtime_lock(runtime)
    httpd = None
    internal_httpd = None
    internal_thread = None
    try:
        httpd = ThreadingHTTPServer((config.bind_host, config.port), Handler)
        internal_httpd = ThreadingHTTPServer((config.internal_bind_host, config.internal_port), Handler)
        engine = None
        if not locked:
            from .engines import Engines
            identity = json.loads((runtime / "runtime-identity.json").read_text())
            if identity.get("release") != config.cortrix_release or identity.get("source_revision") != CORTRIX_COMMIT:
                raise ValueError("The runtime identity does not match the public source pins")
            engine = Engines(runtime_identity=identity, config=config)
        ctl = Controller(runtime, engine, config=config)
        if engine is not None:
            from .provision import RuntimeManager
            ctl.runtime_manager = RuntimeManager(runtime, config=config)
        httpd.controller = ctl
        httpd.surface = "operator"
        internal_httpd.controller = ctl
        internal_httpd.surface = "internal"
        internal_thread = threading.Thread(target=internal_httpd.serve_forever, daemon=True)
        internal_thread.start()
        print(json.dumps({"url": config.operator_origin, "runtime_ready": engine is not None,
                          "internal_url": config.core_callback_base_url, "access_mode": "loopback_operator",
                          "secret_printed": False}), flush=True)
        httpd.serve_forever()
    finally:
        if internal_thread is not None:
            internal_httpd.shutdown()
            internal_thread.join()
        if internal_httpd is not None:
            internal_httpd.server_close()
        if httpd is not None:
            httpd.server_close()
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--locked", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.runtime is not None and args.runtime.resolve() != config.runtime_root:
        raise ValueError("--runtime must match runtime_root in the selected configuration")
    serve(config, locked=args.locked)


if __name__ == "__main__":
    main()
