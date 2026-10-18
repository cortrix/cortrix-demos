from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import LIVE_THREE_PATH_INTEGRATION, SEALED_FULL_STACK_INTEGRATION, default_scenario_id, scenario_entry, scenario_integration_kind
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
    kind = scenario_integration_kind(scenario_entry(repo_root, resolved_id))
    if scenario.get("integration_kind", SEALED_FULL_STACK_INTEGRATION) != kind:
        raise DemoContractError("Scenario integration kind does not match its registry entry")
    if kind == LIVE_THREE_PATH_INTEGRATION:
        return scenario
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


def _validate_sealed_scenario(repo_root: Path, scenario_id: str) -> list[str]:
    resolved_id = scenario_id
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


def _exact_keys(value: object, expected: set[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    actual = set(value)
    if actual != expected:
        return [f"{label} fields must be exactly {sorted(expected)}"]
    return []


def _validate_pending_measurements(path: dict[str, Any], display_stages: list[str]) -> list[str]:
    failures: list[str] = []
    measurements = path.get("measurements")
    failures.extend(_exact_keys(measurements, {"stage_totals", "business_steps"}, f"Path {path.get('id')} measurements"))
    if not isinstance(measurements, dict):
        return failures
    stage_totals = measurements.get("stage_totals")
    if not isinstance(stage_totals, list) or [item.get("stage") for item in stage_totals if isinstance(item, dict)] != display_stages:
        failures.append(f"Path {path.get('id')} must declare the five display-stage totals in order")
    else:
        for item in stage_totals:
            failures.extend(_exact_keys(item, {"stage", "duration_ms", "state"}, f"Path {path.get('id')} stage total"))
            if item.get("duration_ms") is not None or item.get("state") != "pending":
                failures.append(f"Path {path.get('id')} stage totals must remain pending until a live run")
    steps = measurements.get("business_steps")
    if not isinstance(steps, list) or [item.get("operation") for item in steps if isinstance(item, dict)] != ["ingest", "query"]:
        failures.append(f"Path {path.get('id')} must declare independent ingest and query timing")
    else:
        for item in steps:
            failures.extend(_exact_keys(item, {"operation", "owner", "duration_ms", "state"}, f"Path {path.get('id')} business step"))
            if not isinstance(item.get("owner"), str) or not item["owner"] or item.get("duration_ms") is not None or item.get("state") != "pending":
                failures.append(f"Path {path.get('id')} business timing must name an owner and remain pending")
    return failures


def _validate_live_three_path_scenario(repo_root: Path, scenario_id: str) -> list[str]:
    failures: list[str] = []
    try:
        scenario = load_scenario(repo_root, scenario_id)
        validation = load_validation_contract(repo_root, scenario_id)
        contract_path = _scenario_relative_file(repo_root, scenario_id, scenario.get("live_contract"), "Live three-path contract")
        contract = read_json(contract_path)
        fixture_path = _scenario_relative_file(repo_root, scenario_id, scenario.get("fixtures", {}).get("manifest"), "Fixture manifest")
        fixture_manifest = read_json(fixture_path)
    except (DemoContractError, OSError, ValueError) as exc:
        return [str(exc)]

    failures.extend(
        _exact_keys(
            scenario,
            {
                "schema_version", "id", "display_name", "title", "scenario_version", "integration_kind",
                "synthetic_data", "construction_note", "live_contract", "fixtures", "validation_contract", "locales",
            },
            "Live scenario contract",
        )
    )
    entry = scenario_entry(repo_root, scenario_id)
    if "technology_profile" in entry or "accepted_pointer" in entry:
        failures.append("Live candidate registry entries must not declare technology or accepted-evidence pointers")
    if (scenario_root(repo_root, scenario_id) / "evidence").exists():
        failures.append("A contract-only live scenario must not contain an evidence directory")
    if scenario.get("integration_kind") != LIVE_THREE_PATH_INTEGRATION or scenario.get("synthetic_data") is not True:
        failures.append("Live scenario identity or synthetic-data disclosure is invalid")
    locales = scenario.get("locales")
    if locales != {"default": "en-US", "available": ["en-US"]}:
        failures.append("Live scenario must use only the canonical en-US locale")

    expected_contract_keys = {
        "schema_version", "contract_version", "scenario_id", "candidate_state", "runtime_support", "source_pins",
        "input_selection", "display_stages", "business_operations", "paths", "harness_paths", "code_responsibility",
        "provider_usage", "lifecycle",
    }
    failures.extend(_exact_keys(contract, expected_contract_keys, "Live three-path contract"))
    if contract.get("schema_version") != 1 or contract.get("contract_version") != "live_three_path/v1" or contract.get("scenario_id") != scenario_id:
        failures.append("Live three-path contract identity is invalid")
    runtime_manifest_path = "packages/live_demo/manifest.json"
    if contract.get("candidate_state") != "implementation_candidate" or contract.get("runtime_support") != runtime_manifest_path:
        failures.append("Live three-path scenario must identify its implementation candidate manifest")

    failures.extend(
        _exact_keys(
            validation,
            {
                "schema_version", "scenario_id", "contract_version", "source_pins", "input_contract", "display_stages",
                "business_operations", "path_contract", "harness_contract", "responsibility_owners", "fixture_contract",
                "candidate_contract",
            },
            "Live validation contract",
        )
    )
    candidate_rules = validation.get("candidate_contract")
    if (
        validation.get("schema_version") != 1
        or validation.get("contract_version") != "live_three_path/v1"
        or candidate_rules != {
            "state": "implementation_candidate",
            "package_manifest": runtime_manifest_path,
            "accepted_evidence_allowed": False,
            "runtime_results_allowed": False,
        }
    ):
        failures.append("Live validation contract must prohibit runtime and accepted evidence")

    package_root = repo_root / "packages" / "live_demo"
    try:
        implementation = read_json(repo_root / runtime_manifest_path)
    except (DemoContractError, OSError, ValueError) as exc:
        failures.append(f"Live implementation manifest is unavailable: {exc}")
        implementation = {}
    expected_implementation_keys = {
        "schema_version", "package_id", "package_version", "state", "scenario_id", "contract_version",
        "python_package", "cli_entrypoint", "cli_command", "runtime_config_example", "harness_adapter", "fixtures_manifest", "evidence_schema", "source_pins",
        "deterministic_paths", "harness_paths", "display_stages", "business_operations",
        "external_calls_default", "runtime_results_allowed", "accepted_evidence_allowed",
    }
    failures.extend(_exact_keys(implementation, expected_implementation_keys, "Live implementation manifest"))
    if isinstance(implementation, dict):
        expected_identity = {
            "schema_version": 1,
            "package_id": "cortrix-live-demo",
            "package_version": "0.1.0",
            "state": "implementation_candidate",
            "scenario_id": scenario_id,
            "contract_version": "live_three_path/v1",
            "python_package": "src/cortrix_live_demo",
            "cli_entrypoint": "cortrix_live_demo.cli:main",
            "cli_command": "live-democtl",
            "runtime_config_example": "runtime-config.example.json",
            "harness_adapter": "harness/launch.mjs",
            "fixtures_manifest": "runtime-support/fixtures/manifest.json",
            "evidence_schema": "schemas/run-evidence.schema.json",
            "external_calls_default": False,
            "runtime_results_allowed": False,
            "accepted_evidence_allowed": False,
        }
        for key, expected in expected_identity.items():
            if implementation.get(key) != expected:
                failures.append(f"Live implementation manifest has an invalid {key}")
        if implementation.get("source_pins") != contract.get("source_pins"):
            failures.append("Live implementation source pins differ from the scenario contract")
        if implementation.get("deterministic_paths") != ["a0", "a1", "b"] or implementation.get("harness_paths") != ["pg", "b"]:
            failures.append("Live implementation path declarations are invalid")
        if implementation.get("display_stages") != ["input", "write", "search", "result", "code"] or implementation.get("business_operations") != ["ingest", "query"]:
            failures.append("Live implementation stage or operation declarations are invalid")
        for key in ("cli_command", "runtime_config_example", "harness_adapter", "fixtures_manifest", "evidence_schema"):
            relative = implementation.get(key)
            path = (package_root / relative).resolve() if isinstance(relative, str) else package_root
            if not isinstance(relative, str) or not path.is_relative_to(package_root.resolve()) or not path.is_file():
                failures.append(f"Live implementation {key} does not resolve to a package file")
        python_package = implementation.get("python_package")
        python_root = (package_root / python_package).resolve() if isinstance(python_package, str) else package_root
        if not isinstance(python_package, str) or not python_root.is_relative_to(package_root.resolve()) or not (python_root / "__init__.py").is_file():
            failures.append("Live implementation Python package is unavailable")
        runtime_fixture_relative = implementation.get("fixtures_manifest")
        runtime_fixture_path = (package_root / runtime_fixture_relative).resolve() if isinstance(runtime_fixture_relative, str) else package_root
        if isinstance(runtime_fixture_relative, str) and runtime_fixture_path.is_file():
            try:
                runtime_fixture_manifest = read_json(runtime_fixture_path)
                expected_manifest_sha = contract.get("input_selection", {}).get("input_manifest_sha256")
                if sha256_file(runtime_fixture_path) != expected_manifest_sha:
                    failures.append("Live implementation fixture manifest differs from the frozen scenario manifest")
                if runtime_fixture_manifest != fixture_manifest:
                    failures.append("Live implementation fixture declarations differ from the scenario fixtures")
                runtime_fixture_root = runtime_fixture_path.parent
                query = runtime_fixture_manifest.get("query") if isinstance(runtime_fixture_manifest, dict) else None
                failures.extend(_validate_hash(runtime_fixture_root, query, "Live implementation query") if isinstance(query, dict) else ["Live implementation query declaration is missing"])
                documents = runtime_fixture_manifest.get("documents") if isinstance(runtime_fixture_manifest, dict) else None
                if not isinstance(documents, list):
                    failures.append("Live implementation document declarations are missing")
                else:
                    for index, item in enumerate(documents):
                        failures.extend(_validate_hash(runtime_fixture_root, item, f"Live implementation document {index}"))
            except (DemoContractError, OSError, ValueError) as exc:
                failures.append(f"Live implementation fixtures are invalid: {exc}")

    source_pins = contract.get("source_pins")
    failures.extend(_exact_keys(source_pins, {"cortrix", "deepseek_harness"}, "Live source pins"))
    if isinstance(source_pins, dict):
        cortrix = source_pins.get("cortrix")
        harness = source_pins.get("deepseek_harness")
        failures.extend(_exact_keys(cortrix, {"release", "commit"}, "Cortrix source pin"))
        failures.extend(_exact_keys(harness, {"repository", "commit"}, "Harness source pin"))
        if source_pins != validation.get("source_pins"):
            failures.append("Live source pins do not match the reviewed validation contract")

    input_selection = contract.get("input_selection")
    failures.extend(_exact_keys(input_selection, {"fixture_manifest", "input_manifest_sha256", "selection_state"}, "Frozen input selection"))
    if isinstance(input_selection, dict):
        expected_fixture = Path(input_selection.get("fixture_manifest", ""))
        try:
            resolved_fixture = _scenario_relative_file(repo_root, scenario_id, expected_fixture.as_posix(), "Frozen fixture manifest")
            if input_selection.get("input_manifest_sha256") != sha256_file(resolved_fixture):
                failures.append("Frozen input manifest checksum does not match")
            if input_selection.get("input_manifest_sha256") != validation.get("input_contract", {}).get("manifest_sha256"):
                failures.append("Frozen input manifest checksum does not match the reviewed validation contract")
        except DemoContractError as exc:
            failures.append(str(exc))
        if input_selection.get("selection_state") != "frozen_before_execution":
            failures.append("Live input selection must be frozen before execution")

    display_stages = contract.get("display_stages")
    if display_stages != validation.get("display_stages") or display_stages != ["input", "write", "search", "result", "code"]:
        failures.append("Live display stages must be input, write, search, result, and code")
        display_stages = ["input", "write", "search", "result", "code"]
    if contract.get("business_operations") != validation.get("business_operations") or contract.get("business_operations") != ["ingest", "query"]:
        failures.append("Live business operations must be ingest and query")

    paths = contract.get("paths")
    path_ids = [item.get("id") for item in paths if isinstance(item, dict)] if isinstance(paths, list) else []
    path_rules = validation.get("path_contract")
    expected_path_ids = path_rules.get("ids") if isinstance(path_rules, dict) else None
    expected_results = path_rules.get("results") if isinstance(path_rules, dict) else None
    if path_ids != expected_path_ids or path_ids != ["a0", "a1", "b"]:
        failures.append("Live scenario paths must match the reviewed a0, a1, and b order")
    for path in paths if isinstance(paths, list) else []:
        failures.extend(_exact_keys(path, {"id", "role", "backend", "measurements", "result_contract"}, f"Path {path.get('id')}"))
        if not isinstance(path.get("role"), str) or not path["role"] or not isinstance(path.get("backend"), str) or not path["backend"]:
            failures.append(f"Path {path.get('id')} must declare its role and backend")
        result = path.get("result_contract")
        failures.extend(_exact_keys(result, {"selected_field", "source_document", "evidence"}, f"Path {path.get('id')} result contract"))
        if not isinstance(result, dict) or any(not isinstance(result.get(key), str) or not result[key] for key in ("selected_field", "source_document", "evidence")):
            failures.append(f"Path {path.get('id')} result contract is incomplete")
        elif not isinstance(expected_results, dict) or {"selected_field": result["selected_field"], "source_document": result["source_document"]} != expected_results.get(path.get("id")):
            failures.append(f"Path {path.get('id')} deterministic result contract is invalid")
        failures.extend(_validate_pending_measurements(path, display_stages))

    harness_paths = contract.get("harness_paths")
    harness_rules = validation.get("harness_contract")
    expected_harness_ids = harness_rules.get("ids") if isinstance(harness_rules, dict) else None
    harness_bindings = harness_rules.get("scenario_paths") if isinstance(harness_rules, dict) else None
    if not isinstance(harness_paths, list) or [item.get("id") for item in harness_paths if isinstance(item, dict)] != expected_harness_ids or expected_harness_ids != ["pg", "b"]:
        failures.append("Harness paths must be ordered pg and b; Harness must not run a0")
    else:
        for path in harness_paths:
            failures.extend(_exact_keys(path, {"id", "scenario_path", "role", "backend", "result_contract"}, f"Harness path {path.get('id')}"))
            if not isinstance(harness_bindings, dict) or path.get("scenario_path") != harness_bindings.get(path.get("id")) or path.get("scenario_path") == "a0":
                failures.append(f"Harness path {path.get('id')} has an invalid reviewed binding")
            result = path.get("result_contract")
            failures.extend(_exact_keys(result, {"selected_field", "source_document", "evidence"}, f"Harness path {path.get('id')} result contract"))
            expected_result = expected_results.get(path.get("scenario_path")) if isinstance(expected_results, dict) else None
            if not isinstance(result, dict) or {"selected_field": result.get("selected_field"), "source_document": result.get("source_document")} != expected_result or not isinstance(result.get("evidence"), str) or not result["evidence"]:
                failures.append(f"Harness path {path.get('id')} result contract is invalid")

    responsibility = contract.get("code_responsibility")
    expected_owners = validation.get("responsibility_owners")
    if not isinstance(responsibility, list) or [item.get("owner") for item in responsibility if isinstance(item, dict)] != expected_owners:
        failures.append("Code responsibility must match the reviewed owner order")
    elif any(set(item) != {"owner", "methodology"} or not isinstance(item.get("methodology"), str) or not item["methodology"] for item in responsibility):
        failures.append("Every code responsibility must provide a methodology")

    provider_usage = contract.get("provider_usage")
    failures.extend(_exact_keys(provider_usage, {"provider_requests", "cost_estimate_usd", "basis"}, "Provider usage"))
    if not isinstance(provider_usage, dict) or provider_usage.get("provider_requests") is not None or provider_usage.get("cost_estimate_usd") is not None or not isinstance(provider_usage.get("basis"), str) or not provider_usage["basis"]:
        failures.append("Provider requests and cost must remain unclaimed until a live receipt exists")

    lifecycle = contract.get("lifecycle")
    failures.extend(_exact_keys(lifecycle, {"cancel", "resume", "cleanup"}, "Live lifecycle"))
    if isinstance(lifecycle, dict):
        for key in ("cancel", "resume", "cleanup"):
            item = lifecycle.get(key)
            failures.extend(_exact_keys(item, {"required", "receipt", "requirement"}, f"Lifecycle {key}"))
            if not isinstance(item, dict) or item.get("required") is not True or item.get("receipt") != "required" or not isinstance(item.get("requirement"), str):
                failures.append(f"Lifecycle {key} must be required and receipt-backed")

    fixture_rules = validation.get("fixture_contract")
    if not isinstance(fixture_rules, dict) or fixture_rules.get("document_count") != 4:
        failures.append("Live validation contract must require four fixture documents")
    failures.extend(
        _exact_keys(
            fixture_manifest,
            {"schema_version", "synthetic_data", "locale", "construction_note", "provenance", "query", "documents"},
            "Live fixture manifest",
        )
    )
    if fixture_manifest.get("schema_version") != 1 or fixture_manifest.get("synthetic_data") is not True or fixture_manifest.get("locale") != "en-US":
        failures.append("Live fixture manifest identity is invalid")
    if fixture_manifest.get("construction_note") != scenario.get("construction_note"):
        failures.append("Live fixture manifest does not match the scenario construction disclosure")
    provenance = fixture_manifest.get("provenance")
    failures.extend(_exact_keys(provenance, {"kind", "source_scenario", "source_directory", "copy_policy"}, "Live fixture provenance"))
    input_rules = validation.get("input_contract")
    if not isinstance(provenance, dict) or not isinstance(input_rules, dict) or provenance.get("kind") != input_rules.get("provenance_kind") or provenance.get("source_scenario") != input_rules.get("source_scenario"):
        failures.append("Live fixture provenance must identify its reviewed public source")
    documents = fixture_manifest.get("documents")
    expected_document_ids = fixture_rules.get("document_ids") if isinstance(fixture_rules, dict) else None
    if not isinstance(documents, list) or [item.get("document_id") for item in documents if isinstance(item, dict)] != expected_document_ids:
        failures.append("Live fixture manifest must preserve the four reviewed Order API document identities")
    failures.extend(validate_fixture_manifest(repo_root, scenario_id))
    return failures


def validate_scenario(repo_root: Path, scenario_id: str | None = None) -> list[str]:
    resolved_id = resolve_scenario_id(repo_root, scenario_id)
    try:
        kind = scenario_integration_kind(scenario_entry(repo_root, resolved_id))
    except (DemoContractError, OSError, ValueError) as exc:
        return [str(exc)]
    if kind == SEALED_FULL_STACK_INTEGRATION:
        return _validate_sealed_scenario(repo_root, resolved_id)
    if kind == LIVE_THREE_PATH_INTEGRATION:
        return _validate_live_three_path_scenario(repo_root, resolved_id)
    return [f"Unsupported scenario integration kind: {kind}"]
