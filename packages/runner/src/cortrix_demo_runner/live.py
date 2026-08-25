from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any
import urllib.error

from .baseline import export_vectors, run_exact_cosine
from .catalog import load_external_call_policy
from .errors import DemoContractError
from .io import read_json, sha256_file, write_json
from .preflight import REVIEWED_ATTEMPT_LIMITS, full_stack_preflight
from .resolver import apply_lifecycle_resolver
from .secret_profile import secret_value_for_redaction
from .runtime import ROOT, cleanup, compose, contract_smoke, ensure_image, ensure_namespace, identity_map, inspect_namespace, metric_delta, metrics, parse_metrics, request, require_scenario_image_provenance, safe_run_suffix, sanitized_runtime, start, upload, verify_fixture_hashes, verify_models
from .scenario import assertion_contract_path, load_assertion_contract, load_scenario, resolve_scenario_id, scenario_root, validate_scenario


def _live_state_error(message: str) -> DemoContractError:
    """Return a terminal error for execution state that must not be repaired in place."""

    return DemoContractError(message, code="CX_DEMO_LIVE_STATE_INVALID")


def _live_assertion_error(message: str) -> DemoContractError:
    """Return a terminal error for deterministic execution or evidence assertions."""

    return DemoContractError(message, code="CX_DEMO_EXECUTION_ASSERTION_FAILED")


def _live_input_error(message: str, *, next_action: str, **data: Any) -> DemoContractError:
    """Return an actionable error only when correcting the input is safe."""

    return DemoContractError(
        message,
        code="CX_DEMO_LIVE_INPUT_INVALID",
        structured_data={**data, "next_action": next_action},
    )


def new_run_id(scenario_id: str) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{scenario_id}-{timestamp}"


def attempt_ledger_path(root: Path, campaign_id: str | None = None) -> Path:
    if campaign_id is None:
        return root / ".runs" / "attempt-ledger.json"
    return root / ".runs" / "campaigns" / f"{campaign_id}.json"


def attempt_ledger(root: Path, campaign_id: str | None = None) -> dict[str, Any]:
    path = attempt_ledger_path(root, campaign_id)
    if path.exists():
        return read_json(path)
    return {"schema_version": 1, "campaign_id": campaign_id, "full_stack_attempts": []}


def validate_reviewed_attempt_limit(limit: int) -> int:
    if limit not in REVIEWED_ATTEMPT_LIMITS:
        raise _live_input_error(
            "The reviewed Full Stack attempt limit must be 2, 3, 4, or 5",
            next_action="Select one of the reviewed attempt limits before starting Full Stack execution.",
            allowed_attempt_limits=sorted(REVIEWED_ATTEMPT_LIMITS),
            requested_attempt_limit=limit,
        )
    return limit


def reserve_attempt(root: Path, run_id: str, reviewed_attempt_limit: int = 2, campaign_id: str | None = None, scenario_version: str | None = None, demo_commit: str | None = None) -> int:
    path = attempt_ledger_path(root, campaign_id)
    ledger = attempt_ledger(root, campaign_id)
    attempts = ledger.get("full_stack_attempts")
    if not isinstance(attempts, list):
        raise _live_state_error("Full Stack attempt ledger is malformed")
    limit = validate_reviewed_attempt_limit(reviewed_attempt_limit)
    if len(attempts) >= limit:
        raise DemoContractError(
            f"The reviewed {limit}-attempt Full Stack limit has been reached",
            code="CX_DEMO_FULL_STACK_ATTEMPT_LIMIT_REACHED",
            category="quota",
            structured_data={"attempt_limit": limit, "attempts_recorded": len(attempts)},
        )
    number = len(attempts) + 1
    attempts.append({"attempt": number, "run_id": run_id, "scenario_version": scenario_version, "demo_commit": demo_commit, "state": "reserved", "reserved_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    write_json(path, ledger, mode=0o600)
    return number


def update_attempt(root: Path, run_id: str, state: str, category: str | None = None, campaign_id: str | None = None) -> None:
    path = attempt_ledger_path(root, campaign_id)
    ledger = attempt_ledger(root, campaign_id)
    for item in ledger["full_stack_attempts"]:
        if item.get("run_id") == run_id:
            item["state"] = state
            item["failure_category"] = category
            item["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    write_json(path, ledger, mode=0o600)


def verify_demo_checkout(root: Path, *, allow_presentation_localization: bool = True) -> dict[str, str]:
    branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"], check=True, capture_output=True, text=True).stdout.strip()
    checkout_kind = "canonical"
    if branch != "main" and allow_presentation_localization and _is_valid_presentation_checkout(root, branch, commit):
        checkout_kind = "presentation_localization"
    elif branch != "main":
        raise DemoContractError(
            "Full Stack candidate must run from main or a declared presentation localization branch",
            code="CX_DEMO_CHECKOUT_BRANCH_INVALID",
            structured_data={
                "required_branch": "main",
                "actual_branch": branch,
                "presentation_localization_supported": allow_presentation_localization,
                "next_action": "Check out main or a valid declared presentation localization branch, then rerun this command.",
            },
        )
    if status:
        raise DemoContractError(
            "Full Stack candidate must run from a clean working tree",
            code="CX_DEMO_WORKING_TREE_DIRTY",
            # The entry count is reported instead of the paths themselves: status is
            # collected with --untracked-files=all, so the paths can name local files
            # that are not part of the repository.
            structured_data={
                "changed_entry_count": len(status.splitlines()),
                "next_action": "Commit, stash, or discard the changes so the working tree is clean, then rerun this command.",
            },
        )
    if len(commit) != 40:
        raise DemoContractError(
            "Demo repository commit identity is invalid",
            code="CX_DEMO_CHECKOUT_COMMIT_INVALID",
            structured_data={
                "actual_length": len(commit),
                "expected_length": 40,
                "next_action": "Run this command from a full git checkout that resolves HEAD to a 40-character commit.",
            },
        )
    return {"branch": branch, "commit": commit, "working_tree": "clean", "checkout_kind": checkout_kind}


def _is_valid_presentation_checkout(root: Path, branch: str, commit: str) -> bool:
    manifest = root / "localization-base.yaml"
    if not manifest.is_file():
        return False
    try:
        text = manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    required = {
        "canonical_branch": "main",
        "locale": branch,
        "presentation_only": "true",
    }
    for key, expected in required.items():
        matches = re.findall(rf"^{re.escape(key)}[ \t]*:[ \t]*([^#\r\n]+?)[ \t]*$", text, flags=re.MULTILINE)
        if len(matches) != 1 or matches[0].strip() != expected:
            return False
    base_matches = re.findall(r"^canonical_base_commit[ \t]*:[ \t]*([0-9a-f]{40})[ \t]*$", text, flags=re.MULTILINE)
    if len(base_matches) != 1:
        return False
    base_commit = base_matches[0]
    ancestor = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", base_commit, commit],
        capture_output=True,
        check=False,
    )
    if ancestor.returncode != 0:
        return False
    changed = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", f"{base_commit}..{commit}"],
        capture_output=True,
        check=False,
        text=True,
    )
    if changed.returncode != 0:
        return False
    paths = [Path(value) for value in changed.stdout.splitlines() if value]
    if not paths or any(not _is_presentation_localization_path(path) for path in paths):
        raise DemoContractError(
            "The presentation localization branch changes files outside its allowed surface",
            code="CX_DEMO_LOCALIZATION_CHECKOUT_INVALID",
            structured_data={
                "unexpected_path_count": sum(not _is_presentation_localization_path(path) for path in paths),
                "next_action": "Restore the localization branch to presentation-only changes before rerunning live validation.",
            },
        )
    return True


def _is_presentation_localization_path(path: Path) -> bool:
    value = path.as_posix()
    if value in {
        "README.md",
        "README.zh-CN.md",
        "localization-base.yaml",
        "packages/runner/src/cortrix_demo_runner/safety.py",
        "tests/test_public_safety.py",
    }:
        return True
    if value.startswith("docs/") and value.endswith(".zh-CN.md"):
        return True
    if value.startswith("packages/viewer/"):
        return True
    if re.fullmatch(r"scenarios/[^/]+/README\.md", value):
        return True
    if re.fullmatch(r"scenarios/[^/]+/docs/.+\.zh-CN\.md", value):
        return True
    return re.fullmatch(r"scenarios/[^/]+/web/locales/[A-Za-z0-9-]+\.json", value) is not None


def record_state(run_dir: Path, state: str, detail: str | None = None) -> None:
    path = run_dir / "state-history.json"
    history = read_json(path) if path.exists() else {"schema_version": 1, "run_id": run_dir.name, "transitions": []}
    transitions = history.get("transitions")
    if not isinstance(transitions, list):
        raise _live_state_error("Run state history is malformed")
    transition = {"state": state, "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if detail:
        transition["detail"] = detail
    transitions.append(transition)
    write_json(path, history, mode=0o600)


def pricing_cost(pricing: dict[str, Any], input_tokens: int, output_tokens: int) -> float:
    prices = pricing.get("prices_per_million_tokens")
    if not isinstance(prices, dict):
        raise _live_state_error("Pricing snapshot has no token price object")
    input_price = prices.get("input_cache_miss")
    output_price = prices.get("output")
    if not isinstance(input_price, (int, float)) or not isinstance(output_price, (int, float)):
        raise _live_state_error("Pricing snapshot lacks input_cache_miss or output pricing")
    return round((input_tokens * float(input_price) + output_tokens * float(output_price)) / 1_000_000, 8)


def require_budget_bound(profile: dict[str, Any], pricing: dict[str, Any], reviewed_attempt_limit: int | None = None) -> float:
    guard = profile.get("budget_guard")
    if not isinstance(guard, dict):
        raise _live_state_error("Full Stack profile has no budget guard")
    per_attempt_bound = pricing_cost(pricing, int(guard["maximum_input_tokens"]), int(guard["maximum_output_tokens"]))
    attempt_limit = int(profile["max_full_stack_attempts"]) if reviewed_attempt_limit is None else validate_reviewed_attempt_limit(reviewed_attempt_limit)
    bound = round(per_attempt_bound * attempt_limit, 8)
    if bound > float(profile["budget_usd"]):
        raise DemoContractError(
            f"Pricing snapshot makes the Full Stack token bound exceed USD {profile['budget_usd']:.2f}",
            code="CX_DEMO_BUDGET_BOUND_EXCEEDED",
            category="quota",
            structured_data={"budget_usd": float(profile["budget_usd"]), "maximum_contract_cost_usd": bound},
        )
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
        if any(evidence[name] > 0 for name in ("f35_failures", "f38_failures", "f41_failures")):
            raise _live_assertion_error("Full Stack ingestion recorded a deterministic feature failure")
        if completion["pass"]:
            return {"metrics": {**evidence, "completion": completion}, "durable": durable}, after_text
        time.sleep(2)
    raise DemoContractError(
        "Full Stack ingestion timed out",
        code="CX_DEMO_INGESTION_TIMEOUT",
        category="timeout",
        retryable=True,
        retry_after_ms=2000,
        structured_data={"timeout_seconds": timeout_seconds, "expected_document_count": expected_document_count},
    )


def query_payload(query: str, granularity: str) -> dict[str, Any]:
    return {
        "query": query,
        "top_k": 4,
        "rerank": True,
        "include_sources": True,
        "route": "complex",
        "crag": False,
        "granularity": granularity,
        "explain": True,
        "search_config": {"enable_vector": True, "enable_bm25": True, "enable_sql": False},
        "rag_fusion": True,
        "rag_fusion_config": {"enabled": True, "variant_count": 3, "timeout_ms": 120000, "locale": "en", "candidate_multiplier": 5, "max_candidates": 20, "final_rerank": True, "activation_policy": "always"},
        "llm_rerank": True,
        "llm_rerank_config": {"enabled": True, "top_n": 4, "timeout_ms": 120000, "locale": "en", "consensus_runs": 1},
    }


def run_query(namespace: str, query: str, granularity: str) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    payload = query_payload(query, granularity)
    payload["namespaces"] = [namespace]
    before_text = metrics()
    _, response = request("POST", "/query?explain=true", payload, timeout=360)
    after_text = metrics()
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise _live_assertion_error("Full Stack query returned no result list")
    return payload, response, before_text, after_text


def record_query_observation(
    run_dir: Path,
    number: int,
    payload: dict[str, Any],
    response: dict[str, Any],
    before_metrics: str,
    after_metrics: str,
) -> None:
    """Persist raw ignored query evidence before any resolver assertion can fail."""
    write_json(run_dir / "run-b" / f"query-{number:02d}.request.json", payload)
    write_json(run_dir / "run-b" / f"query-{number:02d}.response.json", response)
    (run_dir / "run-b" / f"query-{number:02d}.metrics.before.prom").write_text(before_metrics, encoding="utf-8")
    (run_dir / "run-b" / f"query-{number:02d}.metrics.after.prom").write_text(after_metrics, encoding="utf-8")


def query_assertions(response: dict[str, Any], before_text: str, after_text: str, resolver: dict[str, Any], expected_granularity: str) -> dict[str, Any]:
    explain = response.get("explain")
    dependent = explain.get("llm_dependent_features") if isinstance(explain, dict) else None
    rag = dependent.get("rag_fusion") if isinstance(dependent, dict) else None
    listwise = dependent.get("llm_rerank") if isinstance(dependent, dict) else None
    paths = explain.get("rrf_path_counts") if isinstance(explain, dict) else None
    before = parse_metrics(before_text)
    after = parse_metrics(after_text)
    checks = {
        "chunk_only_result_identity": isinstance(explain, dict) and explain.get("granularity") == expected_granularity == "chunk",
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
        raise _live_assertion_error(f"Full Stack deterministic query assertions failed: {json.dumps(checks, sort_keys=True)}")
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


def run_b(run_id: str, run_dir: Path, fixture_root: Path, manifest: dict[str, Any], frozen_assertions: dict[str, Any], retrieval_contract: dict[str, str]) -> dict[str, Any]:
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
    query_granularity = retrieval_contract["query_granularity"]
    attempts = []
    resolvers = []
    for number in (1, 2):
        payload, response, before, after = run_query(namespace, query, query_granularity)
        record_query_observation(run_dir, number, payload, response, before, after)
        resolver = apply_lifecycle_resolver(response, manifest, identities, frozen_assertions)
        resolver["run_id"] = run_id
        summary = query_assertions(response, before, after, resolver, query_granularity)
        write_json(run_dir / "run-b" / f"resolver-{number:02d}.json", resolver)
        attempts.append(summary)
        resolvers.append(resolver)
    repeat = {
        "result_order_identical": attempts[0]["result_child_ids"] == attempts[1]["result_child_ids"],
        "rerank_scores_identical": attempts[0]["rerank_scores"] == attempts[1]["rerank_scores"],
        "resolver_decision_identical": resolvers[0]["decision"] == resolvers[1]["decision"],
    }
    if not all(repeat.values()):
        raise _live_assertion_error("Two serial Full Stack queries did not preserve the accepted deterministic outputs")
    result = {
        "namespace": namespace,
        "tasks": tasks,
        "ingestion": ingestion["metrics"],
        "query_granularity": query_granularity,
        "document_summary_role": retrieval_contract["document_summary_role"],
        "query_attempts": attempts,
        "repeat": {**repeat, "pass": True},
        "resolver": resolvers[0],
        "pass": True,
    }
    write_json(run_dir / "run-b" / "summary.json", result)
    return result


def run_a(run_id: str, run_dir: Path, fixture_root: Path, manifest: dict[str, Any], frozen_assertions: dict[str, Any], *, runtime_ready: bool = False) -> dict[str, Any]:
    if not runtime_ready:
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
    return run_exact_cosine(document_vectors, query_vectors, fixture_root / "manifest.json", frozen_assertions, run_dir / "run-a" / "pgvector-result.json")


def cost_record(pricing: dict[str, Any], smoke: dict[str, Any], run_b_result: dict[str, Any], bound: float, budget_usd: float) -> dict[str, Any]:
    usage = smoke.get("usage", {})
    input_tokens = int(usage.get("prompt_tokens", 0)) + int(sum(item["rag_fusion_input_tokens"] for item in run_b_result["query_attempts"]))
    output_tokens = int(usage.get("completion_tokens", 0)) + int(sum(item["rag_fusion_output_tokens"] for item in run_b_result["query_attempts"]))
    observed_cost = pricing_cost(pricing, input_tokens, output_tokens)
    return {
        "currency": "USD",
        "budget_usd": budget_usd,
        "maximum_reviewed_attempt_contract_cost_usd": bound,
        "observable_input_tokens": input_tokens,
        "observable_output_tokens": output_tokens,
        "observable_call_count_minimum": 5,
        "model": pricing.get("model"),
        "estimated_observable_cost_usd": observed_cost,
        "estimated_total_usd": None,
        "usage_visibility": "partial",
        "public_cost_claim_allowed": False,
        "within_budget_contract": bound <= budget_usd,
        "pricing_snapshot": pricing,
    }


def source_manifest(run_id: str, attempt: int, campaign_id: str, image: dict[str, str], fixture_manifest: Path, assertion_contract: Path, scenario: dict[str, Any], demo_checkout: dict[str, str]) -> dict[str, Any]:
    technology = read_json(fixture_manifest.parent.parent / "profiles" / "technology-profile.json")
    llm = technology["llm"]
    requires = scenario["requires"]
    return {
        "schema_version": 1,
        "run_id": run_id,
        "attempt": attempt,
        "campaign_id": campaign_id,
        "scenario_id": scenario["id"],
        "scenario_version": scenario["scenario_version"],
        "source": {"cortrix_release": requires["cortrix_release"], "cortrix_release_commit": requires["cortrix_release_commit"], "cortrix_source_revision": requires["cortrix_source_revision"], "container_image": image["image"], "container_digest": image["digest"], "demo_commit": demo_checkout["commit"], "demo_branch": demo_checkout["branch"], "demo_working_tree": demo_checkout["working_tree"]},
        "fixture_manifest_sha256": sha256_file(fixture_manifest),
        "assertion_contract_sha256": sha256_file(assertion_contract),
        "provider": {"provider": llm["provider"], "model": llm["model"], "base_url": llm.get("base_url", "https://api.deepseek.com/v1"), "local_generative_llm": False},
        "private_source_paths_recorded": False,
        "secret_recorded": False,
    }


def finalize_candidate(
    root: Path,
    run_id: str,
    scenario: dict[str, Any],
    attempt: int,
    image: dict[str, str],
    demo_checkout: dict[str, str],
    pricing: dict[str, Any],
    bound: float,
    budget_usd: float,
    preflight: dict[str, Any],
    health: dict[str, Any],
    smoke: dict[str, Any],
    models: dict[str, Any],
    run_a_result: dict[str, Any],
    run_b_result: dict[str, Any],
) -> dict[str, Any]:
    campaign_id = scenario["execution_contract"]["campaign_id"]
    scenario_id = scenario["id"]
    fixture_manifest_path = scenario_root(root, scenario_id) / "fixtures" / "manifest.json"
    assertion_path = assertion_contract_path(root, scenario_id)
    run_dir = root / ".runs" / run_id
    receipt_path = run_dir / "cleanup-receipt.json"
    runtime = sanitized_runtime(run_id, health, image)
    source_identity = source_manifest(run_id, attempt, campaign_id, image, fixture_manifest_path, assertion_path, scenario, demo_checkout)
    cost = cost_record(pricing, smoke, run_b_result, bound, budget_usd)
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
        "f41_document_summary_ingestion": run_b_result["ingestion"]["completion"]["checks"]["f41_all_documents"],
        "chunk_only_result_identity": all(item["checks"]["chunk_only_result_identity"] for item in run_b_result["query_attempts"]),
        "deepseek_ingestion": run_b_result["ingestion"]["completion"]["pass"],
        "deepseek_query_fusion": all(item["checks"]["deepseek_query_fusion"] for item in run_b_result["query_attempts"]),
        "deepseek_listwise_rerank": all(item["checks"]["deepseek_listwise_rerank"] for item in run_b_result["query_attempts"]),
        "application_lifecycle_resolver": run_b_result["resolver"]["pass"],
    }
    assertions = {
        "run_a": run_a_result["pass"],
        "run_b": run_b_result["pass"],
        "required_paths": all(required_paths.values()),
        "resolver": run_b_result["resolver"]["pass"],
        "cleanup": cleanup_result["namespaces_removed"] and cleanup_result["containers_removed"] and cleanup_result["ports_released"] and cleanup_result["runtime_secret_removed"],
        "budget": cost["within_budget_contract"],
        "model_checksums": models["all_match"],
    }
    state = "candidate" if all(assertions.values()) else "rejected"
    run_manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_version": scenario["scenario_version"],
        "campaign_id": campaign_id,
        "campaign_slot": attempt,
        "state": state,
        "target_identity": {"release": scenario["requires"]["cortrix_release"], "release_commit": scenario["requires"]["cortrix_release_commit"], "source_revision": scenario["requires"]["cortrix_source_revision"], "container_digest": image["digest"], "demo_commit": demo_checkout["commit"]},
        "fixture_manifest_sha256": source_identity["fixture_manifest_sha256"],
        "assertion_contract_sha256": source_identity["assertion_contract_sha256"],
        "provider_identity": source_identity["provider"],
        "required_paths": required_paths,
        "run_a": {"path": "run-a/pgvector-result.json", "pass": run_a_result["pass"]},
        "run_b": {
            "path": "run-b/summary.json",
            "pass": run_b_result["pass"],
            "serial_query_count": 2,
            "query_granularity": run_b_result["query_granularity"],
            "document_summary_role": run_b_result["document_summary_role"],
        },
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
        raise _live_assertion_error("Candidate manifest assertions failed")
    record_state(run_dir, "candidate")
    update_attempt(root, run_id, "candidate", campaign_id=campaign_id)
    return run_manifest


def execute_once(root: Path, source: Path, pricing_path: Path, run_id: str, reviewed_attempt_limit: int = 2, *, scenario_id: str | None = None) -> dict[str, Any]:
    resolved_id = resolve_scenario_id(root, scenario_id)
    scenario_failures = validate_scenario(root, resolved_id)
    if scenario_failures:
        raise _live_state_error("Scenario validation failed: " + "; ".join(scenario_failures))
    scenario = load_scenario(root, resolved_id)
    execution_contract = scenario["execution_contract"]
    campaign_id = execution_contract["campaign_id"]
    assertion_contract = load_assertion_contract(root, resolved_id)
    frozen_assertions = assertion_contract["frozen"]
    fixture_root = scenario_root(root, resolved_id) / "fixtures"
    manifest = read_json(fixture_root / "manifest.json")
    profile = read_json(scenario_root(root, resolved_id) / "profiles" / "full-stack.json")
    external_policy = load_external_call_policy(root)
    effective_profile = dict(profile)
    effective_profile["budget_usd"] = min(float(profile["budget_usd"]), float(external_policy["budget_usd"]))
    reviewed_attempt_limit = validate_reviewed_attempt_limit(reviewed_attempt_limit)
    if reviewed_attempt_limit > int(execution_contract["campaign_attempt_cap"]):
        raise DemoContractError(
            "The reviewed attempt limit exceeds the sealed campaign cap",
            code="CX_DEMO_CAMPAIGN_ATTEMPT_CAP_EXCEEDED",
            category="quota",
            structured_data={
                "requested_attempt_limit": reviewed_attempt_limit,
                "campaign_attempt_cap": int(execution_contract["campaign_attempt_cap"]),
            },
        )
    provenance = require_scenario_image_provenance(scenario["requires"])
    technology = read_json(scenario_root(root, resolved_id) / "profiles" / "technology-profile.json")
    preflight = full_stack_preflight(
        source,
        pricing_path,
        release_commit=scenario["requires"]["cortrix_release_commit"],
        source_revision=scenario["requires"]["cortrix_source_revision"],
        source_repository=provenance["source_repository"],
        secret_env=technology["llm"]["secret_env"],
        expected_model=technology["llm"]["model"],
        expected_base_url=technology["llm"]["base_url"],
        reviewed_attempt_limit=reviewed_attempt_limit,
        budget_usd=float(effective_profile["budget_usd"]),
    )
    pricing = read_json(pricing_path)
    bound = require_budget_bound(effective_profile, pricing, reviewed_attempt_limit)
    verify_fixture_hashes(fixture_root, manifest)
    demo_checkout = verify_demo_checkout(root)
    attempt = reserve_attempt(root, run_id, reviewed_attempt_limit, campaign_id, scenario["scenario_version"], demo_checkout["commit"])
    run_dir = root / ".runs" / run_id
    receipt_path = run_dir / "cleanup-receipt.json"
    record_state(run_dir, "created")
    record_state(run_dir, "running")
    image: dict[str, str] = {}
    phase = "image_identity"
    try:
        image = ensure_image(source)
        phase = "run_a_runtime_start"
        start("embedding-only")
        phase = "model_verification"
        models = verify_models()
        write_json(run_dir / "model-checksums.json", models)
        phase = "run_a"
        run_a_result = run_a(run_id, run_dir, fixture_root, manifest, frozen_assertions, runtime_ready=True)
        phase = "run_b_runtime_start"
        health = start("full-stack")
        phase = "provider_contract_smoke"
        smoke = contract_smoke()
        write_json(run_dir / "contract-smoke.json", smoke)
        phase = "run_b"
        run_b_result = run_b(run_id, run_dir, fixture_root, manifest, frozen_assertions, scenario["retrieval_contract"])
        phase = "candidate_finalize"
        return finalize_candidate(
            root,
            run_id,
            scenario,
            attempt,
            image,
            demo_checkout,
            pricing,
            bound,
            float(effective_profile["budget_usd"]),
            preflight,
            health,
            smoke,
            models,
            run_a_result,
            run_b_result,
        )
    except Exception as exc:
        if not receipt_path.exists():
            try:
                cleanup(run_id, receipt_path)
            except Exception:
                pass
        category = failure_category(exc)
        record_state(run_dir, "rejected", category)
        update_attempt(root, run_id, "rejected", category, campaign_id)
        write_json(run_dir / "rejection.json", {"schema_version": 1, "run_id": run_id, "state": "rejected", "phase": phase, "failure_category": category, "message": sanitized_error(exc), "screenshot_eligible": False})
        raise


def failure_category(exc: Exception) -> str:
    if isinstance(exc, DemoContractError):
        if exc.code == "CX_DEMO_HTTP_RATE_LIMITED":
            return "http_429"
        if exc.code == "CX_DEMO_HTTP_SERVER_ERROR":
            return "http_5xx"
        if exc.category == "timeout":
            return "timeout"
    return "deterministic_or_contract_failure"


def sanitized_error(exc: Exception) -> str:
    message = str(exc)
    key = secret_value_for_redaction(
        "DEEPSEEK_API_KEY",
        expected_model="deepseek-v4-flash",
        expected_base_url="https://api.deepseek.com/v1",
    )
    if key:
        message = message.replace(key, "[REDACTED]")
    return message.replace(str(ROOT), "[repository]")


def execute_with_retry(root: Path, source: Path, pricing_path: Path, reviewed_attempt_limit: int = 2, *, scenario_id: str | None = None) -> dict[str, Any]:
    reviewed_attempt_limit = validate_reviewed_attempt_limit(reviewed_attempt_limit)
    resolved_id = resolve_scenario_id(root, scenario_id)
    campaign_id = load_scenario(root, resolved_id)["execution_contract"]["campaign_id"]
    first_id = new_run_id(resolved_id)
    try:
        return execute_once(root, source, pricing_path, first_id, reviewed_attempt_limit, scenario_id=resolved_id)
    except (DemoContractError, subprocess.CalledProcessError, urllib.error.URLError) as first_error:
        category = failure_category(first_error)
        if category not in {"http_429", "http_5xx", "timeout"}:
            raise
        if len(attempt_ledger(root, campaign_id)["full_stack_attempts"]) >= reviewed_attempt_limit:
            raise
        retry_id = new_run_id(resolved_id) + "-retry"
        return execute_once(root, source, pricing_path, retry_id, reviewed_attempt_limit, scenario_id=resolved_id)
