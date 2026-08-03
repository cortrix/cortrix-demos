from __future__ import annotations

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
    selected = next((item for item in candidates if item["eligible_under_policy"]), None)
    if selected is None:
        raise DemoContractError("No retrieved result is current under the application policy")
    resolver = fixture_manifest.get("resolver")
    if not isinstance(resolver, dict):
        raise DemoContractError("Fixture resolver contract is missing")
    expected_document = resolver.get("expected_document_id")
    expected_field = resolver.get("expected_field")
    selected_content = selected.get("content")
    passed = selected["document_id"] == expected_document and isinstance(selected_content, str) and isinstance(expected_field, str) and expected_field in selected_content
    return {
        "schema_version": 1,
        "policy_owner": resolver.get("owner"),
        "policy_rule": resolver.get("rule"),
        "claim_boundary": "Cortrix supplies retrieved content, scores, paths, and durable identity; the demo application owns the lifecycle decision.",
        "candidates": candidates,
        "decision": {
            "selected_document_id": selected["document_id"],
            "selected_version": selected["version"],
            "selected_field": expected_field,
            "reason": "The higher-ranked document is superseded, so the application selects the highest-ranked candidate whose lifecycle status is current.",
        },
        "assertions": {
            "selected_expected_document": selected["document_id"] == expected_document,
            "selected_content_contains_expected_field": isinstance(selected_content, str) and isinstance(expected_field, str) and expected_field in selected_content,
            "retrieval_top1_was_superseded": candidates[0]["lifecycle_status"] == "superseded",
            "resolver_changed_final_document": candidates[0]["document_id"] != selected["document_id"],
        },
        "pass": passed,
    }
