from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from .catalog import default_scenario_id
from .errors import DemoContractError
from .io import read_json, sha256_file


HARNESS_COMPARISON_VARIABLE = "cortrix_bundle_loaded"


def resolve_scenario_id(repo_root: Path, scenario_id: str | None = None) -> str:
    return scenario_id or default_scenario_id(repo_root)


def scenario_root(repo_root: Path, scenario_id: str | None = None) -> Path:
    return repo_root / "scenarios" / resolve_scenario_id(repo_root, scenario_id)


def load_scenario(repo_root: Path, scenario_id: str | None = None) -> dict[str, Any]:
    resolved_id = resolve_scenario_id(repo_root, scenario_id)
    root = scenario_root(repo_root, resolved_id)
    scenario = read_json(root / "scenario.json")
    if scenario.get("schema_version") != 1 or scenario.get("id") != resolved_id:
        raise DemoContractError(
            "Scenario ID does not match its directory",
            code="CX_DEMO_SCENARIO_IDENTITY_INVALID",
            structured_data={"scenario_id": resolved_id, "next_action": "Make scenario.json id match its registered directory name."},
        )
    requires = scenario.get("requires")
    if not isinstance(requires, dict):
        raise DemoContractError("Scenario requires object is missing")
    for key in ("cortrix_release", "cortrix_release_commit", "cortrix_source_revision"):
        value = requires.get(key)
        if not isinstance(value, str) or not value:
            raise DemoContractError(
                f"Scenario source identity is missing {key}",
                code="CX_DEMO_SCENARIO_SOURCE_IDENTITY_INVALID",
                structured_data={"scenario_id": resolved_id, "field": key, "next_action": "Set the missing source identity in scenario.json."},
            )
    return scenario


def _scenario_relative_file(repo_root: Path, scenario_id: str, value: object, label: str) -> Path:
    root = scenario_root(repo_root, scenario_id).resolve()
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise DemoContractError(f"{label} must be a non-empty relative path")
    path = (root / value).resolve()
    if root not in path.parents:
        raise DemoContractError(f"{label} escapes the scenario root")
    if not path.is_file():
        raise DemoContractError(
            f"{label} does not exist",
            structured_data={"scenario_id": scenario_id, "path": value, "next_action": f"Create the registered {label.lower()} file."},
        )
    return path


def validation_contract_path(repo_root: Path, scenario_id: str | None = None) -> Path:
    resolved_id = resolve_scenario_id(repo_root, scenario_id)
    scenario = load_scenario(repo_root, resolved_id)
    return _scenario_relative_file(repo_root, resolved_id, scenario.get("validation_contract"), "Scenario validation contract")


def load_validation_contract(repo_root: Path, scenario_id: str | None = None) -> dict[str, Any]:
    resolved_id = resolve_scenario_id(repo_root, scenario_id)
    contract = read_json(validation_contract_path(repo_root, resolved_id))
    if contract.get("schema_version") != 1 or contract.get("scenario_id") != resolved_id:
        raise DemoContractError("Scenario validation contract identity is invalid")
    return contract


def require_reviewed_retrieval_contract(
    scenario: dict[str, Any],
    validation: dict[str, Any],
) -> None:
    identity = validation.get("scenario_identity")
    if not isinstance(identity, dict):
        raise DemoContractError("Scenario validation identity is missing")
    for key in ("scenario_version", "retrieval_contract", "construction_note", "execution_contract"):
        if scenario.get(key) != identity.get(key):
            raise DemoContractError(
                f"Scenario reviewed identity mismatch for {key}",
                code="CX_DEMO_SCENARIO_CONTRACT_DRIFT",
                structured_data={"scenario_id": scenario.get("id"), "field": key, "next_action": "Review and update the scenario validation contract before changing sealed inputs."},
            )
    if scenario.get("synthetic_data") is not identity.get("synthetic_data"):
        raise DemoContractError("Scenario synthetic data disclosure does not match its validation contract")


def assertion_contract_path(repo_root: Path, scenario_id: str | None = None) -> Path:
    resolved_id = resolve_scenario_id(repo_root, scenario_id)
    scenario = load_scenario(repo_root, resolved_id)
    return _scenario_relative_file(repo_root, resolved_id, scenario.get("assertions"), "Scenario assertion contract")


def load_assertion_contract(repo_root: Path, scenario_id: str | None = None) -> dict[str, Any]:
    resolved_id = resolve_scenario_id(repo_root, scenario_id)
    contract = read_json(assertion_contract_path(repo_root, resolved_id))
    if contract.get("schema_version") != 1 or contract.get("scenario_id") != resolved_id:
        raise DemoContractError("Scenario assertion contract identity is invalid")
    frozen = contract.get("frozen")
    validation = load_validation_contract(repo_root, resolved_id)
    assertion_rules = validation.get("assertion_contract")
    required = assertion_rules.get("required_keys") if isinstance(assertion_rules, dict) else None
    if not isinstance(frozen, dict) or not isinstance(required, list) or not all(isinstance(key, str) for key in required) or not set(required).issubset(frozen):
        raise DemoContractError("Scenario assertion contract is incomplete")
    return contract


def validate_fixture_manifest(repo_root: Path, scenario_id: str | None = None) -> list[str]:
    resolved_id = resolve_scenario_id(repo_root, scenario_id)
    root = scenario_root(repo_root, resolved_id)
    scenario = load_scenario(repo_root, resolved_id)
    fixtures = scenario.get("fixtures")
    manifest_value = fixtures.get("manifest") if isinstance(fixtures, dict) else None
    try:
        manifest_path = _scenario_relative_file(repo_root, resolved_id, manifest_value, "Fixture manifest")
    except DemoContractError as exc:
        return [str(exc)]
    manifest = read_json(manifest_path)
    validation = load_validation_contract(repo_root, resolved_id)
    fixture_rules = validation.get("fixture_contract")
    expected_count = fixture_rules.get("document_count") if isinstance(fixture_rules, dict) else None
    failures: list[str] = []
    query = manifest.get("query")
    if not isinstance(query, dict):
        failures.append("Fixture query object is missing")
    else:
        failures.extend(_validate_hash(manifest_path.parent, query, "query"))
    documents = manifest.get("documents")
    if not isinstance(expected_count, int) or expected_count < 1:
        failures.append("Scenario validation contract has no positive fixture document count")
    elif not isinstance(documents, list) or len(documents) != expected_count:
        failures.append(f"Fixture manifest must contain exactly {expected_count} reviewed documents")
    else:
        for index, document in enumerate(documents):
            if not isinstance(document, dict):
                failures.append(f"Fixture document {index} is not an object")
                continue
            failures.extend(_validate_hash(manifest_path.parent, document, f"document {index}"))
    blind_queries = manifest.get("blind_queries")
    expected_blind_count = fixture_rules.get("blind_query_count") if isinstance(fixture_rules, dict) else None
    if expected_blind_count is not None:
        if not isinstance(expected_blind_count, int) or expected_blind_count < 0:
            failures.append("Scenario validation contract has an invalid blind query count")
        elif not isinstance(blind_queries, list) or len(blind_queries) != expected_blind_count:
            failures.append(f"Fixture manifest must contain exactly {expected_blind_count} reviewed blind queries")
        else:
            blind_ids: list[str] = []
            for index, blind_query in enumerate(blind_queries):
                if not isinstance(blind_query, dict):
                    failures.append(f"Blind query {index} is not an object")
                    continue
                blind_id = blind_query.get("id")
                if not isinstance(blind_id, str) or not blind_id:
                    failures.append(f"Blind query {index} has no stable ID")
                else:
                    blind_ids.append(blind_id)
                failures.extend(_validate_hash(manifest_path.parent, blind_query, f"blind query {index}"))
            if len(blind_ids) != len(set(blind_ids)):
                failures.append("Fixture manifest contains duplicate blind query IDs")
    if isinstance(documents, list) and isinstance(fixture_rules, dict):
        for role, contract_key in (("decisive", "decisive_document_count"), ("distractor", "distractor_document_count")):
            expected_role_count = fixture_rules.get(contract_key)
            if expected_role_count is not None:
                actual_role_count = sum(1 for document in documents if isinstance(document, dict) and document.get("role") == role)
                if not isinstance(expected_role_count, int) or actual_role_count != expected_role_count:
                    failures.append(f"Fixture manifest must contain exactly {expected_role_count} {role} documents")
        if validation.get("baseline_contract") is not None:
            ranks = [document.get("baseline_rank") for document in documents if isinstance(document, dict)]
            if any(not isinstance(rank, int) or rank < 1 for rank in ranks) or len(ranks) != len(set(ranks)):
                failures.append("Fixture documents must have unique positive baseline ranks")
    failures.extend(_validate_position_variants(repo_root, resolved_id, validation, documents))
    return failures


def _validate_position_variants(
    repo_root: Path,
    scenario_id: str,
    validation: dict[str, Any],
    documents: object,
) -> list[str]:
    """Validate frozen event-position variants without treating them as memory."""
    contract = validation.get("position_variant_contract")
    if contract is None:
        return []
    if not isinstance(contract, dict) or not isinstance(documents, list):
        return ["Position variant contract is invalid"]
    fixtures_root = scenario_root(repo_root, scenario_id) / "fixtures"
    path_value = contract.get("path")
    if not isinstance(path_value, str) or Path(path_value).is_absolute():
        return ["Position variant manifest path is invalid"]
    path = fixtures_root / path_value
    if not path.is_file():
        return ["Position variant manifest is missing"]
    manifest = read_json(path)
    expected_ids = contract.get("variant_ids")
    variants = manifest.get("variants")
    failures: list[str] = []
    if manifest.get("schema_version") != 1 or manifest.get("scenario_id") != scenario_id:
        failures.append("Position variant manifest identity is invalid")
    if manifest.get("document_id") != contract.get("document_id") or manifest.get("decisive_event_id") != contract.get("decisive_event_id") or manifest.get("event_count") != contract.get("event_count"):
        failures.append("Position variant manifest does not match its frozen contract")
    if not isinstance(expected_ids, list) or not isinstance(variants, list) or [item.get("id") for item in variants if isinstance(item, dict)] != expected_ids:
        failures.append("Position variants must preserve the frozen front, middle, and end order")
        return failures
    document_ids = {item.get("document_id") for item in documents if isinstance(item, dict)}
    if contract.get("document_id") not in document_ids:
        failures.append("Position variant document is not in the fixture corpus")
    event_sets: list[set[str]] = []
    for variant in variants:
        if not isinstance(variant, dict):
            failures.append("Position variant entry is invalid")
            continue
        failures.extend(_validate_hash(fixtures_root, variant, f"position variant {variant.get('id', 'unknown')}"))
        variant_path = fixtures_root / str(variant.get("path", ""))
        try:
            events = [json.loads(line) for line in variant_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, json.JSONDecodeError):
            failures.append(f"Position variant {variant.get('id')} is not valid JSONL")
            continue
        ids = [event.get("event_id") for event in events if isinstance(event, dict)]
        if len(events) != contract.get("event_count") or len(ids) != len(events) or len(set(ids)) != len(ids):
            failures.append(f"Position variant {variant.get('id')} has an invalid event set")
            continue
        event_sets.append(set(ids))
        decisive_id = contract.get("decisive_event_id")
        actual_index = ids.index(decisive_id) if decisive_id in ids else -1
        if actual_index != variant.get("decisive_event_index"):
            failures.append(f"Position variant {variant.get('id')} decisive event index is invalid")
        variant_id = variant.get("id")
        if variant_id == "front" and actual_index > contract.get("front_max_index", -1):
            failures.append("Front position variant is outside the frozen range")
        if variant_id == "middle" and not contract.get("middle_min_index", 10**9) <= actual_index <= contract.get("middle_max_index", -1):
            failures.append("Middle position variant is outside the frozen range")
        if variant_id == "end" and actual_index < contract.get("end_min_index", 10**9):
            failures.append("End position variant is outside the frozen range")
    if event_sets and any(events != event_sets[0] for events in event_sets[1:]):
        failures.append("Position variants do not contain the same event identities")
    return failures


def _validate_harness_comparison(
    repo_root: Path,
    scenario_id: str,
    scenario: dict[str, Any],
    validation: dict[str, Any],
    frozen: dict[str, Any],
) -> list[str]:
    rules = validation.get("comparison_contract")
    if rules is None:
        return []
    failures: list[str] = []
    comparison = scenario.get("comparison_contract")
    required_true_keys = rules.get("required_true_keys") if isinstance(rules, dict) else None
    if not isinstance(comparison, dict) or not isinstance(required_true_keys, list) or any(not isinstance(key, str) for key in required_true_keys):
        return ["Harness comparison contract is incomplete"]
    if comparison.get("only_independent_variable") != HARNESS_COMPARISON_VARIABLE or rules.get("only_independent_variable") != HARNESS_COMPARISON_VARIABLE:
        failures.append("Harness comparison must isolate Cortrix bundle loading as its only independent variable")
    for key in required_true_keys:
        if comparison.get(key) is not True:
            failures.append(f"Harness comparison contract must keep {key} fixed")
    requires = scenario.get("requires")
    if not isinstance(requires, dict):
        failures.append("Harness comparison source requirements are missing")
    else:
        harness_commit = requires.get("deepseek_harness_commit")
        if not isinstance(harness_commit, str) or len(harness_commit) != 40 or any(character not in "0123456789abcdef" for character in harness_commit):
            failures.append("Harness comparison must pin an exact DeepSeek Harness commit")
        for key in ("cortrix_plugin_package", "cortrix_plugin_version"):
            if not isinstance(requires.get(key), str) or not requires[key]:
                failures.append(f"Harness comparison source requirements are missing {key}")
    baseline_contract = validation.get("baseline_contract")
    if not isinstance(baseline_contract, dict):
        failures.append("Harness comparison baseline contract is missing")
        return failures
    path_value = baseline_contract.get("path")
    if not isinstance(path_value, str) or not path_value or Path(path_value).is_absolute():
        failures.append("Harness comparison baseline path is invalid")
        return failures
    baseline_path = scenario_root(repo_root, scenario_id) / "expected" / path_value
    if not baseline_path.is_file():
        failures.append("Harness comparison baseline contract file is missing")
        return failures
    baseline = read_json(baseline_path)
    top_k = baseline_contract.get("top_k")
    document_ids = baseline.get("document_ids")
    manifest = read_json(scenario_root(repo_root, scenario_id) / "fixtures" / "manifest.json")
    documents = manifest.get("documents")
    by_id = {item.get("document_id"): item for item in documents if isinstance(item, dict)} if isinstance(documents, list) else {}
    if baseline.get("schema_version") != 1 or baseline.get("scenario_id") != scenario_id or baseline.get("provider") != baseline_contract.get("provider"):
        failures.append("Harness comparison baseline identity is invalid")
    if not isinstance(top_k, int) or top_k < 1 or not isinstance(document_ids, list) or len(document_ids) != top_k or len(set(document_ids)) != top_k:
        failures.append("Harness comparison baseline ranking is invalid")
    elif any(document_id not in by_id for document_id in document_ids):
        failures.append("Harness comparison baseline ranking references an unknown document")
    else:
        expected_top_key = baseline_contract.get("expected_top_document_assertion")
        if not isinstance(expected_top_key, str) or document_ids[0] != frozen.get(expected_top_key):
            failures.append("Harness comparison baseline top result does not match the frozen assertion")
        ordered = [item.get("document_id") for item in sorted(by_id.values(), key=lambda item: item.get("baseline_rank", 10**9))[:top_k]]
        if document_ids != ordered:
            failures.append("Harness comparison baseline ranking does not match preregistered fixture order")
    return failures


def _validate_hash(fixtures_root: Path, item: dict[str, Any], label: str) -> list[str]:
    path_value = item.get("path")
    expected = item.get("sha256")
    if not isinstance(path_value, str) or not path_value:
        return [f"{label} path is missing"]
    path = fixtures_root / path_value
    if not path.is_file():
        return [f"{label} file is missing: {path_value}"]
    actual = sha256_file(path)
    if expected != actual:
        return [f"{label} checksum mismatch: {path_value}"]
    return []


def validate_scenario(repo_root: Path, scenario_id: str | None = None) -> list[str]:
    resolved_id = resolve_scenario_id(repo_root, scenario_id)
    failures: list[str] = []
    try:
        scenario = load_scenario(repo_root, resolved_id)
        validation = load_validation_contract(repo_root, resolved_id)
    except (DemoContractError, OSError, ValueError) as exc:
        return [str(exc)]
    if scenario.get("evidence_schema") != 1:
        failures.append("Evidence schema must be version 1")
    try:
        require_reviewed_retrieval_contract(scenario, validation)
    except DemoContractError as exc:
        failures.append(str(exc))
    locales = scenario.get("locales")
    if not isinstance(locales, dict) or not isinstance(locales.get("default"), str) or locales.get("default") not in locales.get("available", []):
        failures.append("Scenario locale bundle must include its default locale")
    profile = read_json(scenario_root(repo_root, resolved_id) / "profiles" / "full-stack.json")
    profile_rules = validation.get("full_stack_profile")
    if not isinstance(profile_rules, dict):
        failures.append("Scenario validation contract has no Full Stack profile rules")
    else:
        for key in ("budget_usd", "max_full_stack_attempts", "local_generative_llm"):
            if profile.get(key) != profile_rules.get(key):
                failures.append(f"Full Stack profile does not match the scenario contract for {key}")
        required_paths = profile.get("required_paths")
        expected_paths = profile_rules.get("required_paths")
        if not isinstance(required_paths, list) or not isinstance(expected_paths, list) or len(required_paths) != len(set(required_paths)) or set(required_paths) != set(expected_paths):
            failures.append("Full Stack profile does not declare the scenario's exact required paths")
    failures.extend(validate_fixture_manifest(repo_root, resolved_id))
    try:
        contract = load_assertion_contract(repo_root, resolved_id)
    except (DemoContractError, OSError, ValueError) as exc:
        failures.append(str(exc))
        return failures
    frozen = contract["frozen"]
    fixture_manifest = read_json(scenario_root(repo_root, resolved_id) / "fixtures" / "manifest.json")
    documents = fixture_manifest.get("documents")
    by_id = {item.get("document_id"): item for item in documents if isinstance(item, dict)} if isinstance(documents, list) else {}
    document_pairs = validation.get("document_assertion_pairs")
    if not isinstance(document_pairs, list):
        failures.append("Scenario validation contract has no document assertion pairs")
    else:
        for pair in document_pairs:
            document_key = pair.get("document_key") if isinstance(pair, dict) else None
            status_key = pair.get("status_key") if isinstance(pair, dict) else None
            document = by_id.get(frozen.get(document_key))
            if not isinstance(document_key, str) or not isinstance(status_key, str) or not isinstance(document, dict) or document.get("status") != frozen.get(status_key):
                failures.append(f"Scenario document assertion does not match a fixture document: {document_key}")
    list_rules = validation.get("document_list_assertions")
    if isinstance(list_rules, list):
        for rule in list_rules:
            key = rule.get("key") if isinstance(rule, dict) else None
            count = rule.get("count") if isinstance(rule, dict) else None
            values = frozen.get(key)
            if not isinstance(key, str) or not isinstance(count, int) or not isinstance(values, list) or len(values) != count or len(set(values)) != count or any(value not in by_id for value in values):
                failures.append(f"Scenario document list assertion is invalid: {key}")
    if fixture_manifest.get("synthetic_data") is not scenario.get("synthetic_data") or fixture_manifest.get("construction_note") != scenario.get("construction_note"):
        failures.append("Fixture manifest does not match the scenario construction disclosure")
    resolver_rules = validation.get("resolver_contract")
    resolver = fixture_manifest.get("resolver")
    if isinstance(resolver_rules, dict):
        expected_document_key = resolver_rules.get("expected_document_assertion")
        expected_field_key = resolver_rules.get("expected_field_assertion")
        expected_action_key = resolver_rules.get("expected_action_assertion")
        expected_action = resolver_rules.get("expected_action")
        if not isinstance(resolver, dict) or resolver.get("expected_document_id") != frozen.get(expected_document_key) or resolver.get("expected_field") != frozen.get(expected_field_key):
            failures.append("Fixture resolver does not match the scenario assertion contract")
        if frozen.get(expected_action_key) != expected_action:
            failures.append("Scenario resolver action does not match its validation contract")
    failures.extend(_validate_harness_comparison(repo_root, resolved_id, scenario, validation, frozen))
    return failures
