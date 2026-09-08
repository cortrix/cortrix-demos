"""Validate an unmodified final answer against the actual visible tool evidence."""
import hashlib
import json
import re

CONTRACT = "cortrix_live_demo_answer/v1"
KEYS = {"selected_field", "document_id", "evidence_ref"}


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def validate_answer(raw, projection, policy):
    assertions = dict.fromkeys(("json_syntax_valid", "decision_is_object", "exact_keys",
        "field_types_valid", "not_abstained", "field_matches_observed_policy",
        "document_matches_observed_policy", "citation_matches_returned_current_document",
        "field_present_in_visible_evidence"), False)
    result = {"contract": CONTRACT, "business_verdict": "fail", "decision": None,
              "assertions": assertions, "failure_codes": [], "abstained": False,
              "raw_answer_sha256": hashlib.sha256(raw.encode()).hexdigest() if isinstance(raw, str) else None,
              "normalization_applied": False}

    def failure(code):
        result["failure_codes"].append(code)
        return result

    if not isinstance(raw, str) or not raw.strip():
        return failure("empty_final_answer")
    try:
        decision = json.loads(raw, object_pairs_hook=unique_object,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON value")))
    except (ValueError, TypeError):
        return failure("invalid_json_or_duplicate_keys")
    assertions["json_syntax_valid"] = True
    if not isinstance(decision, dict):
        return failure("decision_not_object")
    assertions["decision_is_object"] = True
    if set(decision) != KEYS:
        return failure("unexpected_decision_keys")
    assertions["exact_keys"] = True
    result["decision"] = decision
    if all(value is None for value in decision.values()):
        assertions["field_types_valid"] = True
        result["abstained"] = True
        return failure("explicit_abstention")
    if any(not isinstance(value, str) or not value.strip() for value in decision.values()):
        return failure("invalid_decision_field_types")
    assertions["field_types_valid"] = True
    assertions["not_abstained"] = True
    expected_field = policy.get("selected_field")
    expected_document = policy.get("selected_document_id")
    assertions["field_matches_observed_policy"] = expected_field not in {None, "unknown", ""} and decision["selected_field"] == expected_field
    assertions["document_matches_observed_policy"] = expected_document not in {None, "unknown", ""} and decision["document_id"] == expected_document
    candidates = [item for item in projection.get("evidence", [])
                  if item.get("evidence_ref") == decision["evidence_ref"]]
    source = candidates[0] if len(candidates) == 1 else None
    assertions["citation_matches_returned_current_document"] = bool(source and source.get("document_id") == decision["document_id"] and source.get("lifecycle_status") == "current")
    if source and isinstance(source.get("content"), str):
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(decision["selected_field"]) + r"(?![A-Za-z0-9_])"
        assertions["field_present_in_visible_evidence"] = re.search(pattern, source["content"]) is not None
    if projection.get("operation") != "query" or projection.get("status") != "ok":
        return failure("successful_query_receipt_required")
    result["failure_codes"] = [name for name, passed in assertions.items() if not passed]
    result["business_verdict"] = "pass" if not result["failure_codes"] else "fail"
    return result
