from __future__ import annotations

import math
from typing import Any

from .errors import DemoContractError


def apply_lifecycle_resolver(
    response: dict[str, Any],
    fixture_manifest: dict[str, Any],
    identity_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    results = response.get("results")
    if not isinstance(results, list) or not results:
        raise DemoContractError("Query response has no results")
    documents = fixture_manifest.get("documents")
    if not isinstance(documents, list):
        raise DemoContractError("Fixture manifest has no documents")
    by_document_id = {
        item.get("document_id"): item
        for item in documents
        if isinstance(item, dict) and isinstance(item.get("document_id"), str)
    }
    candidates: list[dict[str, Any]] = []
    for rank, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            raise DemoContractError(f"Result {rank} is not an object")
        child_id = result.get("child_id")
        if not isinstance(child_id, str) or child_id not in identity_map:
            raise DemoContractError(f"Result {rank} lacks a durable child identity mapping")
        durable = identity_map[child_id]
        document_id = durable.get("document_id")
        fixture = by_document_id.get(document_id)
        if not isinstance(fixture, dict):
            raise DemoContractError(f"Result {rank} maps to an unknown fixture document")
        candidates.append(
            {
                "final_response_rank": rank,
                "retrieval_rank": rank,
                "child_id": child_id,
                "doc_id": durable.get("doc_id"),
                "document_id": document_id,
                "version": fixture.get("version"),
                "lifecycle_status": fixture.get("status"),
                "source": fixture.get("source"),
                "score": result.get("score"),
                "rerank_score": result.get("rerank_score"),
                "content": result.get("content"),
                "eligible_under_policy": fixture.get("status") == "current",
            }
        )
    if len(candidates) < 2:
        raise DemoContractError("Layered ranking requires at least two durable candidates")
    for candidate in candidates:
        rerank_score = candidate.get("rerank_score")
        if isinstance(rerank_score, bool) or not isinstance(rerank_score, (int, float)) or not math.isfinite(float(rerank_score)):
            raise DemoContractError("Every candidate must expose a finite BGE rerank score")
    bge_order = sorted(candidates, key=lambda item: (-float(item["rerank_score"]), int(item["final_response_rank"])))
    for rank, candidate in enumerate(bge_order, start=1):
        candidate["bge_rerank_rank"] = rank
    bge_leader = bge_order[0]
    bge_runner_up = bge_order[1]
    final_top = candidates[0]
    selected = next((item for item in candidates if item["eligible_under_policy"]), None)
    if selected is None:
        raise DemoContractError("No retrieved result is current under the application policy")
    resolver = fixture_manifest.get("resolver")
    if not isinstance(resolver, dict):
        raise DemoContractError("Fixture resolver contract is missing")
    expected_document = resolver.get("expected_document_id")
    expected_field = resolver.get("expected_field")
    selected_content = selected.get("content")
    assertions = {
        "selected_expected_document": selected["document_id"] == expected_document,
        "selected_content_contains_expected_field": isinstance(selected_content, str) and isinstance(expected_field, str) and expected_field in selected_content,
        "bge_rerank_leader_was_superseded": bge_leader["lifecycle_status"] == "superseded",
        "bge_rerank_leader_was_strict": float(bge_leader["rerank_score"]) > float(bge_runner_up["rerank_score"]),
        "final_top1_is_current": final_top["lifecycle_status"] == "current",
        "policy_preserved_final_top1": final_top["document_id"] == selected["document_id"],
    }
    passed = all(assertions.values())
    reason = (
        f"The highest BGE cross-encoder score belongs to {bge_leader['document_id']} ({bge_leader['lifecycle_status']}). "
        f"The Full Stack final response places {final_top['document_id']} ({final_top['lifecycle_status']}) first. "
        f"The application lifecycle policy independently selects {selected['document_id']} and "
        f"{'preserves' if final_top['document_id'] == selected['document_id'] else 'changes'} the final top result."
    )

    def layer_result(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "document_id": candidate["document_id"],
            "version": candidate["version"],
            "lifecycle_status": candidate["lifecycle_status"],
            "final_response_rank": candidate["final_response_rank"],
            "bge_rerank_rank": candidate["bge_rerank_rank"],
            "bge_rerank_score": candidate["rerank_score"],
        }

    return {
        "schema_version": 2,
        "policy_owner": resolver.get("owner"),
        "policy_rule": resolver.get("rule"),
        "claim_boundary": "Cortrix supplies the final response order, BGE rerank scores, retrieval paths, content, and durable identity. The demo application independently owns lifecycle validation; no single ranking layer is business truth.",
        "candidates": candidates,
        "layers": {
            "bge_cross_encoder": {
                "meaning": "Candidate order by descending BGE cross-encoder rerank score before the final listwise order is applied.",
                "leader": layer_result(bge_leader),
            },
            "deepseek_listwise_final": {
                "meaning": "Final result order returned by the configured Cortrix Full Stack query.",
                "top_result": layer_result(final_top),
            },
            "application_lifecycle_policy": {
                "meaning": "Independent defense-in-depth validation that selects the highest final-ranked current document.",
                "action": "preserved_final_top1" if final_top["document_id"] == selected["document_id"] else "changed_final_top1",
            },
        },
        "decision": {
            "selected_document_id": selected["document_id"],
            "selected_version": selected["version"],
            "selected_field": expected_field,
            "reason": reason,
        },
        "assertions": assertions,
        "pass": passed,
    }
