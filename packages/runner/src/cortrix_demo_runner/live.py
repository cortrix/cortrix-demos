from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any
import urllib.error

from .baseline import export_vectors, run_exact_cosine
from .errors import DemoContractError
from .io import read_json, sha256_file, write_json
from .preflight import full_stack_preflight
from .resolver import apply_lifecycle_resolver
from .runtime import ROOT, cleanup, compose, contract_smoke, ensure_image, ensure_namespace, identity_map, inspect_namespace, metric_delta, metrics, parse_metrics, request, safe_run_suffix, sanitized_runtime, start, upload, verify_fixture_hashes, verify_models
from .scenario import RELEASE, RELEASE_COMMIT, SCENARIO_ID, SOURCE_REVISION, scenario_root


def new_run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("order-api-field-migration-%Y%m%dT%H%M%SZ")


def attempt_ledger(root: Path) -> dict[str, Any]:
    path = root / ".runs" / "attempt-ledger.json"
    if path.exists():
        return read_json(path)
    return {"schema_version": 1, "full_stack_attempts": []}


def reserve_attempt(root: Path, run_id: str) -> int:
    path = root / ".runs" / "attempt-ledger.json"
    ledger = attempt_ledger(root)
    attempts = ledger.get("full_stack_attempts")
    if not isinstance(attempts, list):
        raise DemoContractError("Full Stack attempt ledger is malformed")
    if len(attempts) >= 2:
        raise DemoContractError("The two-attempt Full Stack limit has been reached")
    number = len(attempts) + 1
    attempts.append({"attempt": number, "run_id": run_id, "state": "reserved", "reserved_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    write_json(path, ledger, mode=0o600)
    return number


def update_attempt(root: Path, run_id: str, state: str, category: str | None = None) -> None:
    path = root / ".runs" / "attempt-ledger.json"
    ledger = attempt_ledger(root)
    for item in ledger["full_stack_attempts"]:
        if item.get("run_id") == run_id:
            item["state"] = state
            item["failure_category"] = category
            item["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    write_json(path, ledger, mode=0o600)


def verify_demo_checkout(root: Path) -> dict[str, str]:
    branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"], check=True, capture_output=True, text=True).stdout.strip()
    if branch != "main":
        raise DemoContractError("Full Stack candidate must run from the main branch")
    if status:
        raise DemoContractError("Full Stack candidate must run from a clean working tree")
    if len(commit) != 40:
        raise DemoContractError("Demo repository commit identity is invalid")
    return {"branch": branch, "commit": commit, "working_tree": "clean"}


def record_state(run_dir: Path, state: str, detail: str | None = None) -> None:
    path = run_dir / "state-history.json"
    history = read_json(path) if path.exists() else {"schema_version": 1, "run_id": run_dir.name, "transitions": []}
    transitions = history.get("transitions")
    if not isinstance(transitions, list):
        raise DemoContractError("Run state history is malformed")
    transition = {"state": state, "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if detail:
        transition["detail"] = detail
    transitions.append(transition)
    write_json(path, history, mode=0o600)


def pricing_cost(pricing: dict[str, Any], input_tokens: int, output_tokens: int) -> float:
    prices = pricing.get("prices_per_million_tokens")
    if not isinstance(prices, dict):
        raise DemoContractError("Pricing snapshot has no token price object")
    input_price = prices.get("input_cache_miss")
    output_price = prices.get("output")
    if not isinstance(input_price, (int, float)) or not isinstance(output_price, (int, float)):
        raise DemoContractError("Pricing snapshot lacks input_cache_miss or output pricing")
    return round((input_tokens * float(input_price) + output_tokens * float(output_price)) / 1_000_000, 8)


def require_budget_bound(profile: dict[str, Any], pricing: dict[str, Any]) -> float:
    guard = profile.get("budget_guard")
    if not isinstance(guard, dict):
        raise DemoContractError("Full Stack profile has no budget guard")
    per_attempt_bound = pricing_cost(pricing, int(guard["maximum_input_tokens"]), int(guard["maximum_output_tokens"]))
    bound = round(per_attempt_bound * int(profile["max_full_stack_attempts"]), 8)
    if bound > float(profile["budget_usd"]):
        raise DemoContractError(f"Pricing snapshot makes the Full Stack token bound exceed USD {profile['budget_usd']:.2f}")
    return bound


def ingest_documents(run_id: str, namespace: str, fixture_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_namespace(namespace)
    tasks = []
    for item in manifest["documents"]:
        path = fixture_root / item["path"]
        metadata = {key: value for key, value in item.items() if key != "sha256"}
        metadata.update({"demo_run_id": run_id, "fixture_sha256": item["sha256"]})
        tasks.append(upload(namespace, path.name, path.read_text(encoding="utf-8"), metadata))
    return tasks


def ingestion_completion(
    evidence: dict[str, Any],
    durable: dict[str, Any],
    expected_document_count: int,
    hype_questions_per_chunk: int,
) -> dict[str, Any]:
    text_blocks = durable.get("text_blocks")
    text_block_count = len(text_blocks) if isinstance(text_blocks, list) else 0
    expected_hype_questions = text_block_count * hype_questions_per_chunk
    checks = {
        "all_documents_materialized": text_block_count >= expected_document_count,
        "f03_all_chunks": evidence["f03_llm_enriched_chunks"] >= text_block_count,
        "f35_all_chunks": evidence["f35_contextualized_chunks"] >= text_block_count,
        "f38_all_chunks": evidence["hype_questions"] >= expected_hype_questions,
        "f41_all_documents": evidence["document_summaries"] >= expected_document_count,
        "enrich_state_all_chunks": evidence["enrich_state_ok"] >= text_block_count,
    }
    return {
        "expected_document_count": expected_document_count,
        "expected_text_block_count": text_block_count,
        "hype_questions_per_chunk": hype_questions_per_chunk,
        "expected_hype_question_count": expected_hype_questions,
        "checks": checks,
        "pass": all(checks.values()),
    }


def wait_enrichment(namespace: str, before_text: str, expected_document_count: int, hype_questions_per_chunk: int = 3, timeout_seconds: float = 900) -> tuple[dict[str, Any], str]:
    deadline = time.monotonic() + timeout_seconds
    last = {}
    while time.monotonic() < deadline:
        after_text = metrics()
        durable = inspect_namespace(namespace)
        before = parse_metrics(before_text)
        after = parse_metrics(after_text)
        evidence = {
            "f03_llm_enriched_chunks": metric_delta(before, after, "cortrix_enricher_score_duration_seconds_count"),
            "f35_contextualized_chunks": metric_delta(before, after, 'cortrix_contextual_retrieval_chunks_total{status="generated"}'),
            "f35_failures": metric_delta(before, after, 'cortrix_contextual_retrieval_chunks_total{status="failed"}'),
            "f38_failures": metric_delta(before, after, 'cortrix_hype_index_llm_calls_total{status="failed"}'),
            "f41_document_summaries": metric_delta(before, after, 'cortrix_doc_summary_llm_calls_total{status="success"}'),
            "f41_failures": metric_delta(before, after, 'cortrix_doc_summary_llm_calls_total{status="failed"}'),
            "hype_questions": durable.get("hype_question_count", 0),
            "document_summaries": durable.get("document_summary_count", 0),
            "enrich_state_ok": durable.get("enrich_state_ok_count", 0),
        }
        completion = ingestion_completion(evidence, durable, expected_document_count, hype_questions_per_chunk)
        last = {**evidence, "completion": completion}
        if any(evidence[name] > 0 for name in ("f35_failures", "f38_failures", "f41_failures")):
            raise DemoContractError("Full Stack ingestion recorded a deterministic feature failure")
        if completion["pass"]:
            return {"metrics": {**evidence, "completion": completion}, "durable": durable}, after_text
        time.sleep(2)
    raise DemoContractError(f"Full Stack ingestion timed out. transient_category=timeout evidence={json.dumps(last, sort_keys=True)}")


def query_payload(query: str) -> dict[str, Any]:
    return {
        "query": query,
        "top_k": 2,
        "rerank": True,
        "include_sources": True,
        "route": "complex",
        "crag": False,
        "granularity": "both",
        "explain": True,
        "search_config": {"enable_vector": True, "enable_bm25": True, "enable_sql": False},
        "rag_fusion": True,
        "rag_fusion_config": {"enabled": True, "variant_count": 3, "timeout_ms": 120000, "locale": "en", "candidate_multiplier": 5, "max_candidates": 20, "final_rerank": True, "activation_policy": "always"},
        "llm_rerank": True,
        "llm_rerank_config": {"enabled": True, "top_n": 2, "timeout_ms": 120000, "locale": "en", "consensus_runs": 1},
    }


def run_query(namespace: str, query: str) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    payload = query_payload(query)
    payload["namespaces"] = [namespace]
    before_text = metrics()
    _, response = request("POST", "/query?explain=true", payload, timeout=360)
    after_text = metrics()
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise DemoContractError("Full Stack query returned no result list")
    return payload, response, before_text, after_text


def query_assertions(response: dict[str, Any], before_text: str, after_text: str, resolver: dict[str, Any]) -> dict[str, Any]:
    explain = response.get("explain")
    dependent = explain.get("llm_dependent_features") if isinstance(explain, dict) else None
    rag = dependent.get("rag_fusion") if isinstance(dependent, dict) else None
    listwise = dependent.get("llm_rerank") if isinstance(dependent, dict) else None
    paths = explain.get("rrf_path_counts") if isinstance(explain, dict) else None
    before = parse_metrics(before_text)
    after = parse_metrics(after_text)
    checks = {
        "bm25_recall": isinstance(paths, dict) and float(paths.get("fts5", paths.get("bm25", 0))) > 0,
        "contextualized_recall": isinstance(paths, dict) and float(paths.get("contextualized", 0)) > 0,
        "hype_recall": isinstance(paths, dict) and float(paths.get("hype_question", 0)) > 0,
        "rrf_fusion": isinstance(rag, dict) and rag.get("active") is True and rag.get("degraded") is not True and metric_delta(before, after, 'cortrix_rag_fusion_invocation_total{result="success"}') == 1,
        "bge_cross_encoder_rerank": metric_delta(before, after, "cortrix_reranker_score_duration_seconds_count") > 0,
        "deepseek_query_fusion": isinstance(rag, dict) and rag.get("active") is True and rag.get("degraded") is not True,
        "deepseek_listwise_rerank": isinstance(listwise, dict) and listwise.get("active") is True and listwise.get("degraded") is not True and listwise.get("model") == "deepseek-v4-flash",
        "application_lifecycle_resolver": resolver.get("pass") is True,
    }
    if not all(checks.values()):
        raise DemoContractError(f"Full Stack deterministic query assertions failed: {json.dumps(checks, sort_keys=True)}")
    return {
        "checks": checks,
        "rrf_path_counts": paths,
        "rag_fusion": rag,
        "llm_listwise_rerank": listwise,
        "result_child_ids": [item.get("child_id") for item in response["results"]],
        "rerank_scores": [item.get("rerank_score") for item in response["results"]],
        "rag_fusion_input_tokens": metric_delta(before, after, 'cortrix_rag_fusion_token_total{direction="input"}'),
        "rag_fusion_output_tokens": metric_delta(before, after, 'cortrix_rag_fusion_token_total{direction="output"}'),
        "pass": True,
    }


def run_b(run_id: str, run_dir: Path, fixture_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    namespace = "order-b-" + safe_run_suffix(run_id)
    before_ingest = metrics()
    tasks = ingest_documents(run_id, namespace, fixture_root, manifest)
    ingestion, after_ingest = wait_enrichment(namespace, before_ingest, expected_document_count=len(manifest["documents"]))
    write_json(run_dir / "run-b" / "durable-inspection.json", ingestion["durable"])
    (run_dir / "run-b" / "metrics-before-ingest.prom").write_text(before_ingest, encoding="utf-8")
    (run_dir / "run-b" / "metrics-after-ingest.prom").write_text(after_ingest, encoding="utf-8")
    identities = identity_map(ingestion["durable"])
    write_json(run_dir / "run-b" / "identity-map.json", identities)
    query = (fixture_root / manifest["query"]["path"]).read_text(encoding="utf-8").strip()
    attempts = []
    resolvers = []
    for number in (1, 2):
        payload, response, before, after = run_query(namespace, query)
        resolver = apply_lifecycle_resolver(response, manifest, identities)
        resolver["run_id"] = run_id
        summary = query_assertions(response, before, after, resolver)
        write_json(run_dir / "run-b" / f"query-{number:02d}.request.json", payload)
        write_json(run_dir / "run-b" / f"query-{number:02d}.response.json", response)
        write_json(run_dir / "run-b" / f"resolver-{number:02d}.json", resolver)
        (run_dir / "run-b" / f"query-{number:02d}.metrics.before.prom").write_text(before, encoding="utf-8")
        (run_dir / "run-b" / f"query-{number:02d}.metrics.after.prom").write_text(after, encoding="utf-8")
        attempts.append(summary)
        resolvers.append(resolver)
    repeat = {
        "result_order_identical": attempts[0]["result_child_ids"] == attempts[1]["result_child_ids"],
        "rerank_scores_identical": attempts[0]["rerank_scores"] == attempts[1]["rerank_scores"],
        "resolver_decision_identical": resolvers[0]["decision"] == resolvers[1]["decision"],
    }
    if not all(repeat.values()):
        raise DemoContractError("Two serial Full Stack queries did not preserve the accepted deterministic outputs")
    result = {"namespace": namespace, "tasks": tasks, "ingestion": ingestion["metrics"], "query_attempts": attempts, "repeat": {**repeat, "pass": True}, "resolver": resolvers[0], "pass": True}
    write_json(run_dir / "run-b" / "summary.json", result)
    return result


def run_a(run_id: str, run_dir: Path, fixture_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    start("embedding-only")
    suffix = safe_run_suffix(run_id)
    documents_namespace = "order-a-docs-" + suffix
    query_namespace = "order-a-query-" + suffix
    ingest_documents(run_id, documents_namespace, fixture_root, manifest)
    ensure_namespace(query_namespace)
    query_path = fixture_root / manifest["query"]["path"]
    upload(query_namespace, "query-anchor.txt", query_path.read_text(encoding="utf-8"), {"document_id": "query-anchor", "role": "query_embedding_anchor", "demo_run_id": run_id})
    document_vectors = run_dir / "run-a" / "document-vectors.json"
    query_vectors = run_dir / "run-a" / "query-vectors.json"
    document_vectors.parent.mkdir(parents=True, exist_ok=True)
    export_vectors(documents_namespace, document_vectors)
    export_vectors(query_namespace, query_vectors)
    return run_exact_cosine(document_vectors, query_vectors, fixture_root / "manifest.json", run_dir / "run-a" / "pgvector-result.json")


def cost_record(pricing: dict[str, Any], smoke: dict[str, Any], run_b_result: dict[str, Any], bound: float) -> dict[str, Any]:
    usage = smoke.get("usage", {})
    input_tokens = int(usage.get("prompt_tokens", 0)) + int(sum(item["rag_fusion_input_tokens"] for item in run_b_result["query_attempts"]))
    output_tokens = int(usage.get("completion_tokens", 0)) + int(sum(item["rag_fusion_output_tokens"] for item in run_b_result["query_attempts"]))
    observed_cost = pricing_cost(pricing, input_tokens, output_tokens)
    return {
        "currency": "USD",
        "budget_usd": 1.0,
        "maximum_two_attempt_contract_cost_usd": bound,
        "observable_input_tokens": input_tokens,
        "observable_output_tokens": output_tokens,
        "observable_call_count_minimum": 5,
        "model": "deepseek-v4-flash",
        "estimated_observable_cost_usd": observed_cost,
        "estimated_total_usd": None,
        "usage_visibility": "partial",
        "public_cost_claim_allowed": False,
        "within_budget_contract": bound <= 1.0,
        "pricing_snapshot": pricing,
    }


def source_manifest(run_id: str, attempt: int, image: dict[str, str], fixture_manifest: Path, demo_checkout: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "attempt": attempt,
        "scenario_id": SCENARIO_ID,
        "source": {"cortrix_release": RELEASE, "cortrix_release_commit": RELEASE_COMMIT, "cortrix_source_revision": SOURCE_REVISION, "container_image": image["image"], "container_digest": image["digest"], "demo_commit": demo_checkout["commit"], "demo_branch": demo_checkout["branch"], "demo_working_tree": demo_checkout["working_tree"]},
        "fixture_manifest_sha256": sha256_file(fixture_manifest),
        "provider": {"provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/v1", "local_generative_llm": False},
        "private_source_paths_recorded": False,
        "secret_recorded": False,
    }


def execute_once(root: Path, source: Path, pricing_path: Path, run_id: str) -> dict[str, Any]:
    fixture_root = scenario_root(root) / "fixtures"
    fixture_manifest_path = fixture_root / "manifest.json"
    manifest = read_json(fixture_manifest_path)
    profile = read_json(scenario_root(root) / "profiles" / "full-stack.json")
    preflight = full_stack_preflight(source, pricing_path)
    pricing = read_json(pricing_path)
    bound = require_budget_bound(profile, pricing)
    verify_fixture_hashes(fixture_root, manifest)
    demo_checkout = verify_demo_checkout(root)
    attempt = reserve_attempt(root, run_id)
    run_dir = root / ".runs" / run_id
    receipt_path = run_dir / "cleanup-receipt.json"
    record_state(run_dir, "created")
    record_state(run_dir, "running")
    image: dict[str, str] = {}
    phase = "image_identity"
    try:
        image = ensure_image(source)
        phase = "runtime_start"
        health = start("full-stack")
        phase = "model_verification"
        models = verify_models()
        write_json(run_dir / "model-checksums.json", models)
        phase = "provider_contract_smoke"
        smoke = contract_smoke()
        write_json(run_dir / "contract-smoke.json", smoke)
        phase = "run_b"
        run_b_result = run_b(run_id, run_dir, fixture_root, manifest)
        phase = "run_a"
        run_a_result = run_a(run_id, run_dir, fixture_root, manifest)
        phase = "runtime_identity"
        health = start("full-stack")
        runtime = sanitized_runtime(run_id, health, image)
        source_identity = source_manifest(run_id, attempt, image, fixture_manifest_path, demo_checkout)
        cost = cost_record(pricing, smoke, run_b_result, bound)
        write_json(run_dir / "preflight.json", preflight)
        write_json(run_dir / "runtime.json", runtime)
        write_json(run_dir / "source-manifest.json", source_identity)
        cleanup_result = cleanup(run_id, receipt_path)
        required_paths = {
            "bge_m3_embedding": models["all_match"],
            "bm25_recall": all(item["checks"]["bm25_recall"] for item in run_b_result["query_attempts"]),
            "contextualized_recall": all(item["checks"]["contextualized_recall"] for item in run_b_result["query_attempts"]),
            "hype_recall": all(item["checks"]["hype_recall"] for item in run_b_result["query_attempts"]),
            "rrf_fusion": all(item["checks"]["rrf_fusion"] for item in run_b_result["query_attempts"]),
            "bge_cross_encoder_rerank": all(item["checks"]["bge_cross_encoder_rerank"] for item in run_b_result["query_attempts"]),
            "deepseek_ingestion": run_b_result["ingestion"]["completion"]["pass"],
            "deepseek_query_fusion": all(item["checks"]["deepseek_query_fusion"] for item in run_b_result["query_attempts"]),
            "deepseek_listwise_rerank": all(item["checks"]["deepseek_listwise_rerank"] for item in run_b_result["query_attempts"]),
            "application_lifecycle_resolver": run_b_result["resolver"]["pass"],
        }
        assertions = {"run_a": run_a_result["pass"], "run_b": run_b_result["pass"], "required_paths": all(required_paths.values()), "resolver": run_b_result["resolver"]["pass"], "cleanup": cleanup_result["namespaces_removed"] and cleanup_result["containers_removed"] and cleanup_result["ports_released"] and cleanup_result["runtime_secret_removed"], "budget": cost["within_budget_contract"], "model_checksums": models["all_match"]}
        state = "candidate" if all(assertions.values()) else "rejected"
        run_manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "scenario_id": SCENARIO_ID,
            "state": state,
            "target_identity": {"release": RELEASE, "release_commit": RELEASE_COMMIT, "source_revision": SOURCE_REVISION, "container_digest": image["digest"], "demo_commit": demo_checkout["commit"]},
            "fixture_manifest_sha256": source_identity["fixture_manifest_sha256"],
            "provider_identity": source_identity["provider"],
            "required_paths": required_paths,
            "run_a": {"path": "run-a/pgvector-result.json", "pass": run_a_result["pass"]},
            "run_b": {"path": "run-b/summary.json", "pass": run_b_result["pass"], "serial_query_count": 2},
            "resolver": {"path": "run-b/resolver-01.json", "pass": run_b_result["resolver"]["pass"]},
            "cleanup": {"path": "cleanup-receipt.json", **cleanup_result},
            "cost": cost,
            "assertions": {**assertions, "all_passed": all(assertions.values())},
            "disclosed_gaps": [
                {"id": "usage-visibility-partial", "blocking_public_cost_claim": True, "note": "Internal ingestion and listwise calls do not expose complete token usage; only observable usage and a conservative budget bound are recorded."},
                {"id": "hype-provider-attribution", "blocking_runtime_acceptance": False, "note": "HyPE attribution relies on the sole configured external provider endpoint, exact runtime revision, durable HyPE blocks, and no-local-LLM contract because rc.1 durable labels are not authoritative provider identity."},
                {"id": "result-source-identity", "blocking_runtime_acceptance": False, "note": "The application resolver uses the durable child_id to doc_id to fixture document_id map instead of trusting source_doc_id."},
            ],
            "claim_boundary": run_b_result["resolver"]["claim_boundary"],
            "screenshot_eligible": False,
            "human_review_required": True,
        }
        write_json(run_dir / "run-manifest.json", run_manifest)
        if state != "candidate":
            raise DemoContractError("Candidate manifest assertions failed")
        record_state(run_dir, "candidate")
        update_attempt(root, run_id, "candidate")
        return run_manifest
    except Exception as exc:
        if not receipt_path.exists():
            try:
                cleanup(run_id, receipt_path)
            except Exception:
                pass
        category = failure_category(exc)
        record_state(run_dir, "rejected", category)
        update_attempt(root, run_id, "rejected", category)
        write_json(run_dir / "rejection.json", {"schema_version": 1, "run_id": run_id, "state": "rejected", "phase": phase, "failure_category": category, "message": sanitized_error(exc), "screenshot_eligible": False})
        raise


def failure_category(exc: Exception) -> str:
    text = str(exc)
    for category in ("http_429", "http_5xx", "timeout"):
        if f"transient_category={category}" in text:
            return category
    return "deterministic_or_contract_failure"


def sanitized_error(exc: Exception) -> str:
    message = str(exc)
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        message = message.replace(key, "[REDACTED]")
    return message.replace(str(ROOT), "[repository]")


def execute_with_retry(root: Path, source: Path, pricing_path: Path) -> dict[str, Any]:
    first_id = new_run_id()
    try:
        return execute_once(root, source, pricing_path, first_id)
    except (DemoContractError, subprocess.CalledProcessError, urllib.error.URLError) as first_error:
        category = failure_category(first_error)
        if category not in {"http_429", "http_5xx", "timeout"}:
            raise
        if len(attempt_ledger(root)["full_stack_attempts"]) >= 2:
            raise
        retry_id = new_run_id() + "-retry"
        return execute_once(root, source, pricing_path, retry_id)
