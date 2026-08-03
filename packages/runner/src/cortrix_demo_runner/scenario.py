from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import DemoContractError
from .io import read_json, sha256_file


SCENARIO_ID = "order-api-field-migration"
RELEASE = "v1.0.0-rc.1"
RELEASE_COMMIT = "e159974f936bd987d5718195d54cd70ff3acc2e5"
SOURCE_REVISION = "32b82f6f8f1d7a41349f408969ff03b7997b6c15"


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
    locales = scenario.get("locales")
    if locales != {"default": "en-US", "available": ["en-US"]}:
        failures.append("Official locale bundle must contain only en-US")
    profile = read_json(scenario_root(repo_root, scenario_id) / "profiles" / "full-stack.json")
    if profile.get("budget_usd") != 1.0:
        failures.append("Full Stack budget must be USD 1.00")
    if profile.get("max_full_stack_attempts") != 2:
        failures.append("Full Stack attempts must be capped at two")
    if profile.get("local_generative_llm") is not False:
        failures.append("Local generative LLM must be disabled")
    failures.extend(validate_fixture_manifest(repo_root, scenario_id))
    return failures
