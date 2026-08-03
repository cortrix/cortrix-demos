from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import DemoContractError
from .io import read_json, sha256_file


SCENARIO_ID = "order-api-field-migration"
RELEASE = "v1.0.0-rc.1"
RELEASE_COMMIT = "e159974f936bd987d5718195d54cd70ff3acc2e5"
SOURCE_REVISION = "32b82f6f8f1d7a41349f408969ff03b7997b6c15"
EXPECTED_RETRIEVAL_CONTRACT = {"query_granularity": "chunk", "document_summary_role": "ingestion_evidence_only"}
REQUIRED_LAYERED_ASSERTIONS = {
    "run_a_dense_cosine_top_document_id",
    "run_a_dense_cosine_top_document_status",
    "run_b_bge_rerank_leader_document_id",
    "run_b_bge_rerank_leader_status",
    "run_b_final_top_document_id",
    "run_b_final_top_document_status",
    "resolver_selected_document_id",
    "resolver_selected_field",
    "resolver_action",
}
REQUIRED_FULL_STACK_PATHS = {
    "bge_m3_embedding",
    "bm25_recall",
    "contextualized_recall",
    "hype_recall",
    "rrf_fusion",
    "bge_cross_encoder_rerank",
    "f41_document_summary_ingestion",
    "chunk_only_result_identity",
    "deepseek_ingestion",
    "deepseek_query_fusion",
    "deepseek_listwise_rerank",
    "application_lifecycle_resolver",
}


def scenario_root(repo_root: Path, scenario_id: str = SCENARIO_ID) -> Path:
    return repo_root / "scenarios" / scenario_id


def load_scenario(repo_root: Path, scenario_id: str = SCENARIO_ID) -> dict[str, Any]:
    root = scenario_root(repo_root, scenario_id)
    scenario = read_json(root / "scenario.json")
    if scenario.get("id") != scenario_id:
        raise DemoContractError("Scenario ID does not match its directory")
    requires = scenario.get("requires")
    if not isinstance(requires, dict):
        raise DemoContractError("Scenario requires object is missing")
    expected = {
        "cortrix_release": RELEASE,
        "cortrix_release_commit": RELEASE_COMMIT,
        "cortrix_source_revision": SOURCE_REVISION,
    }
    for key, value in expected.items():
        if requires.get(key) != value:
            raise DemoContractError(f"Scenario identity mismatch for {key}")
    return scenario


def require_reviewed_retrieval_contract(scenario: dict[str, Any]) -> None:
    if scenario.get("scenario_version") != "1.2.0" or scenario.get("retrieval_contract") != EXPECTED_RETRIEVAL_CONTRACT:
        raise DemoContractError("Scenario must preserve the reviewed 1.2.0 chunk-only retrieval contract")


def assertion_contract_path(repo_root: Path, scenario_id: str = SCENARIO_ID) -> Path:
    root = scenario_root(repo_root, scenario_id).resolve()
    scenario = load_scenario(repo_root, scenario_id)
    value = scenario.get("assertions")
    if not isinstance(value, str) or not value:
        raise DemoContractError("Scenario assertion contract path is missing")
    path = (root / value).resolve()
    if root not in path.parents:
        raise DemoContractError("Scenario assertion contract path escapes the scenario root")
    return path


def load_assertion_contract(repo_root: Path, scenario_id: str = SCENARIO_ID) -> dict[str, Any]:
    contract = read_json(assertion_contract_path(repo_root, scenario_id))
    if contract.get("schema_version") != 1 or contract.get("scenario_id") != scenario_id:
        raise DemoContractError("Scenario assertion contract identity is invalid")
    frozen = contract.get("frozen")
    if not isinstance(frozen, dict) or not REQUIRED_LAYERED_ASSERTIONS.issubset(frozen):
        raise DemoContractError("Scenario layered-ranking assertions are incomplete")
    return contract


def validate_fixture_manifest(repo_root: Path, scenario_id: str = SCENARIO_ID) -> list[str]:
    root = scenario_root(repo_root, scenario_id)
    manifest_path = root / "fixtures" / "manifest.json"
    manifest = read_json(manifest_path)
    failures: list[str] = []
    query = manifest.get("query")
    if not isinstance(query, dict):
        failures.append("Fixture query object is missing")
    else:
        failures.extend(_validate_hash(root / "fixtures", query, "query"))
    documents = manifest.get("documents")
    if not isinstance(documents, list) or len(documents) != 2:
        failures.append("Fixture manifest must contain exactly two documents")
    else:
        for index, document in enumerate(documents):
            if not isinstance(document, dict):
                failures.append(f"Fixture document {index} is not an object")
                continue
            failures.extend(_validate_hash(root / "fixtures", document, f"document {index}"))
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


def validate_scenario(repo_root: Path, scenario_id: str = SCENARIO_ID) -> list[str]:
    failures: list[str] = []
    try:
        scenario = load_scenario(repo_root, scenario_id)
    except DemoContractError as exc:
        return [str(exc)]
    if scenario.get("evidence_schema") != 1:
        failures.append("Evidence schema must be version 1")
    try:
        require_reviewed_retrieval_contract(scenario)
    except DemoContractError as exc:
        failures.append(str(exc))
    locales = scenario.get("locales")
    if locales != {"default": "en-US", "available": ["en-US"]}:
        failures.append("Official locale bundle must contain only en-US")
    profile = read_json(scenario_root(repo_root, scenario_id) / "profiles" / "full-stack.json")
    if profile.get("budget_usd") != 5.0:
        failures.append("Full Stack budget must be USD 5.00")
    if profile.get("max_full_stack_attempts") != 2:
        failures.append("Full Stack attempts must be capped at two")
    if profile.get("local_generative_llm") is not False:
        failures.append("Local generative LLM must be disabled")
    required_paths = profile.get("required_paths")
    if not isinstance(required_paths, list) or set(required_paths) != REQUIRED_FULL_STACK_PATHS or len(required_paths) != len(REQUIRED_FULL_STACK_PATHS):
        failures.append("Full Stack profile must declare the exact reviewed required paths")
    failures.extend(validate_fixture_manifest(repo_root, scenario_id))
    try:
        contract = load_assertion_contract(repo_root, scenario_id)
    except (DemoContractError, OSError, ValueError) as exc:
        failures.append(str(exc))
        return failures
    frozen = contract["frozen"]
    fixture_manifest = read_json(scenario_root(repo_root, scenario_id) / "fixtures" / "manifest.json")
    documents = fixture_manifest.get("documents")
    by_id = {item.get("document_id"): item for item in documents if isinstance(item, dict)} if isinstance(documents, list) else {}
    expected_documents = (
        ("run_a_dense_cosine_top_document_id", "run_a_dense_cosine_top_document_status"),
        ("run_b_bge_rerank_leader_document_id", "run_b_bge_rerank_leader_status"),
        ("run_b_final_top_document_id", "run_b_final_top_document_status"),
    )
    for document_key, status_key in expected_documents:
        document = by_id.get(frozen.get(document_key))
        if not isinstance(document, dict) or document.get("status") != frozen.get(status_key):
            failures.append(f"Layered assertion {document_key} does not match a fixture document and status")
    resolver = fixture_manifest.get("resolver")
    if not isinstance(resolver, dict) or resolver.get("expected_document_id") != frozen.get("resolver_selected_document_id") or resolver.get("expected_field") != frozen.get("resolver_selected_field"):
        failures.append("Fixture resolver does not match the layered assertion contract")
    if frozen.get("resolver_action") != "preserved_final_top1":
        failures.append("Layered assertion resolver action must preserve the final top result")
    return failures
