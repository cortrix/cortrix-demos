"""Public contract constants and repository fixture validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import CONTRACT_VERSION, CORTRIX_COMMIT, CORTRIX_RELEASE, HARNESS_COMMIT, HARNESS_REPOSITORY, SCENARIO_ID


FIXTURE_MANIFEST_SHA256 = "67f179dfecd7a410c38ca8c726ad8d59197193badc710f15154f6dd23d405cd2"
DISPLAY_STAGES = ("input", "write", "search", "result", "code")
BUSINESS_OPERATIONS = ("ingest", "query")
DETERMINISTIC_PATHS = ("a0", "a1", "b")
HARNESS_PATHS = ("pg", "b")
HARNESS_SCENARIO_PATHS = {"pg": "a1", "b": "b"}
RESPONSIBILITY_OWNERS = ("demo_runner", "application", "cortrix")
RESULT_CONTRACTS = {
    "a0": {"selected_field": "account_id", "source_document": "order-api-guide-v1.0"},
    "a1": {"selected_field": "buyer_account_id", "source_document": "order-api-release-v2.0"},
    "b": {"selected_field": "buyer_account_id", "source_document": "order-api-release-v2.0"},
}


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_fixture_bytes(path: Path, expected_sha256: str) -> bytes:
    """Return bytes matching the public checksum, allowing one text-transform newline."""
    raw = path.read_bytes()
    if sha256(raw) == expected_sha256:
        return raw
    if raw.endswith(b"\n") and sha256(raw[:-1]) == expected_sha256:
        return raw[:-1]
    raise ValueError(f"Fixture identity mismatch: {path.name}")


def validate_fixture_set(root: Path | str) -> dict:
    """Validate the exact public fixture contract without executing a runtime."""
    root = Path(root).resolve()
    manifest_path = (root / "manifest.json").resolve()
    if not manifest_path.is_relative_to(root) or not manifest_path.is_file():
        raise ValueError("The fixture manifest is missing")
    raw = manifest_path.read_bytes()
    # Permit one extra terminal newline introduced by a source-control text transform.
    source_bytes = raw[:-1] if raw.endswith(b"\n\n") else raw
    if sha256(source_bytes) != FIXTURE_MANIFEST_SHA256:
        raise ValueError("The fixture manifest does not match live_three_path/v1")
    manifest = json.loads(raw)
    if manifest.get("locale") != "en-US" or manifest.get("synthetic_data") is not True:
        raise ValueError("The live demo requires the public synthetic en-US fixture profile")
    query = manifest.get("query") or {}
    items = [(query.get("path"), query.get("sha256"))]
    items.extend((item.get("path"), item.get("sha256")) for item in manifest.get("documents", []))
    if len(items) != 5:
        raise ValueError("The fixture contract requires one query and four documents")
    for relative, expected in items:
        path = (root / str(relative)).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Fixture identity mismatch: {relative}")
        read_fixture_bytes(path, expected)
    return manifest


def contract_mapping() -> dict:
    return {
        "scenario_id": SCENARIO_ID,
        "contract_version": CONTRACT_VERSION,
        "candidate_state": "implementation_candidate",
        "implementation_state": "implementation_candidate",
        "source_pins": {
            "cortrix": {"release": CORTRIX_RELEASE, "commit": CORTRIX_COMMIT},
            "deepseek_harness": {"repository": HARNESS_REPOSITORY, "commit": HARNESS_COMMIT},
        },
        "input_manifest_sha256": FIXTURE_MANIFEST_SHA256,
        "display_stages": list(DISPLAY_STAGES),
        "business_operations": list(BUSINESS_OPERATIONS),
        "deterministic_paths": list(DETERMINISTIC_PATHS),
        "harness_paths": list(HARNESS_PATHS),
        "harness_scenario_paths": HARNESS_SCENARIO_PATHS,
        "result_contracts": RESULT_CONTRACTS,
        "responsibility_owners": list(RESPONSIBILITY_OWNERS),
        "accepted_evidence_allowed": False,
        "runtime_results_allowed": False,
    }
