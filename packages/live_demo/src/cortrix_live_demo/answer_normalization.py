"""Normalize a recorded answer only when its unique JSON is evidence-bound."""
import hashlib
import json

KEYS = {"selected_field", "document_id", "evidence_ref"}


def normalize_answer(raw, run_id, path, query):
    strict = True
    try:
        candidate = json.loads(raw.strip())
        candidates = [candidate] if isinstance(candidate, dict) and set(candidate) == KEYS else []
    except (ValueError, TypeError):
        strict = False
        candidates = []
        decoder = json.JSONDecoder()
        for offset, character in enumerate(raw):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(raw[offset:])
            except ValueError:
                continue
            if isinstance(candidate, dict) and set(candidate) == KEYS:
                candidates.append(candidate)
    result = {"schema_version": 1, "verified": False, "original_strict_json": strict,
              "original_answer_sha256": hashlib.sha256(raw.encode()).hexdigest(), "reason": "ambiguous_or_missing_json"}
    if len(candidates) != 1:
        return result
    decision = candidates[0]
    if any(not isinstance(decision[key], str) or not decision[key] for key in KEYS):
        return {**result, "reason": "invalid_decision_fields"}
    source = next((item for item in query["ranking"][:8] if f"{run_id}:{path}:{item['rank']}:{item.get('document_id')}" == decision["evidence_ref"]), None)
    policy = query["resolver"]
    if not source or source.get("lifecycle_status") != "current" or decision["document_id"] != source["document_id"] or decision["document_id"] != policy["selected_document_id"] or decision["selected_field"] != policy["selected_field"] or decision["selected_field"] in {None, "unknown"}:
        return {**result, "reason": "decision_does_not_match_current_returned_evidence"}
    visible = str(source.get("content") or source.get("parent_content") or "").encode()[:2048].decode("utf-8", errors="ignore")
    if decision["selected_field"] not in visible:
        return {**result, "reason": "field_not_present_in_visible_evidence"}
    return {**result, "verified": True, "decision": decision, "reason": "unique_json_and_current_evidence_verified",
            "normalization_applied": not strict}
