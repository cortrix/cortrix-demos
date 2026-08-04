from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import default_scenario_id
from .errors import DemoContractError
from .io import read_json, sha256_file


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
    return failures
