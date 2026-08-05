from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from typing import Any
import zlib

from .errors import DemoContractError
from .io import read_json, sha256_file, write_json
from .live import verify_demo_checkout
from .safety import scan_text
from .scenario import assertion_contract_path, load_assertion_contract, load_scenario, load_validation_contract, require_reviewed_retrieval_contract, resolve_scenario_id, scenario_root


COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
CLEAN_ROOM_REVIEW_PATTERN = re.compile(r"^REVIEW-[A-Z0-9-]+$")
SCREENSHOT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.png$")
REQUIRED_CANDIDATE_FILES = (
    "run-manifest.json",
    "source-manifest.json",
    "runtime.json",
    "contract-smoke.json",
    "model-checksums.json",
    "cleanup-receipt.json",
    "state-history.json",
    "run-a/pgvector-result.json",
    "run-b/summary.json",
    "run-b/resolver-01.json",
    "run-b/resolver-02.json",
)
ALLOWED_CURATED_FILES = {
    "run-manifest.json",
    "target-identity.json",
    "runtime.json",
    "contract-smoke.json",
    "pricing-snapshot.json",
    "fixture-manifest.json",
    "assertion-contract.json",
    "model-checksums.json",
    "assertions.json",
    "cleanup-receipt.json",
    "state-history.json",
    "checksums.json",
    "run-a/pgvector-result.json",
    "run-b/summary.json",
    "run-b/resolver-01.json",
    "run-b/resolver-02.json",
    "screenshots/screenshot-manifest.json",
}
LAYERED_RESOLVER_ASSERTIONS = {
    "selected_expected_document",
    "selected_content_contains_expected_field",
    "required_documents_retrieved",
    "bge_scores_present",
    "final_top1_matches_contract",
    "policy_action_matches_contract",
}


def _acceptance_integrity_error(message: str) -> DemoContractError:
    """Return a terminal error for evidence that must never be repaired in place."""

    return DemoContractError(message, code="CX_DEMO_ACCEPTANCE_INTEGRITY_VIOLATION")


def _acceptance_input_error(message: str, *, next_action: str) -> DemoContractError:
    """Return an actionable error only when changing command input is safe."""

    return DemoContractError(
        message,
        code="CX_DEMO_ACCEPTANCE_INPUT_INVALID",
        structured_data={"next_action": next_action},
    )


def _screenshot_input_error(message: str) -> DemoContractError:
    """Return an actionable error for a source image that can be recaptured safely."""

    return DemoContractError(
        message,
        code="CX_DEMO_SCREENSHOT_INPUT_INVALID",
        structured_data={"next_action": "Capture a complete PNG from the accepted evidence viewer, then rerun the screenshot command."},
    )


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _acceptance_integrity_error(f"{label} must be a JSON object")
    return value


def candidate_root(root: Path, run_id: str) -> Path:
    return root / ".runs" / run_id


def accepted_root(root: Path, run_id: str, scenario_id: str | None = None) -> Path:
    return scenario_root(root, scenario_id) / "evidence" / "runs" / run_id


def validate_run_id(root: Path, scenario_id: str, run_id: str) -> None:
    validation = load_validation_contract(root, scenario_id)
    evidence = validation.get("evidence_contract")
    pattern = evidence.get("run_id_pattern") if isinstance(evidence, dict) else None
    if not isinstance(pattern, str) or not re.fullmatch(pattern, run_id):
        raise DemoContractError(
            "Run ID does not match the selected scenario format",
            code="CX_DEMO_RUN_ID_INVALID",
            structured_data={"scenario_id": scenario_id, "run_id": run_id, "next_action": "Use a run ID produced by the selected scenario executor."},
        )


def validate_manifest_contract(root: Path, scenario_id: str, manifest: dict[str, Any]) -> str:
    scenario = load_scenario(root, scenario_id)
    validation = load_validation_contract(root, scenario_id)
    evidence = require_object(validation.get("evidence_contract"), "Scenario evidence contract")
    technology = read_json(scenario_root(root, scenario_id) / "profiles" / "technology-profile.json")
    llm = require_object(technology.get("llm"), "Scenario LLM profile")
    if manifest.get("schema_version") != 1 or manifest.get("scenario_id") != scenario_id:
        raise _acceptance_integrity_error("Run schema or scenario identity is invalid")
    assertions = manifest.get("assertions")
    assertion_names = evidence.get("required_manifest_assertions")
    if not isinstance(assertion_names, list) or not all(isinstance(name, str) for name in assertion_names):
        raise _acceptance_integrity_error("Scenario evidence assertion requirements are invalid")
    if not isinstance(assertions, dict) or not all(assertions.get(name) is True for name in assertion_names):
        raise _acceptance_integrity_error("Run assertions are incomplete or failed")
    required_paths = manifest.get("required_paths")
    profile_rules = require_object(validation.get("full_stack_profile"), "Scenario Full Stack profile rules")
    required_path_names = profile_rules.get("required_paths")
    if not isinstance(required_path_names, list) or not isinstance(required_paths, dict) or set(required_paths) != set(required_path_names) or not all(value is True for value in required_paths.values()):
        raise _acceptance_integrity_error("Run required-path evidence is incomplete, substituted, or failed")
    target = manifest.get("target_identity")
    demo_commit = target.get("demo_commit") if isinstance(target, dict) else None
    if not isinstance(demo_commit, str) or not COMMIT_PATTERN.fullmatch(demo_commit):
        raise _acceptance_integrity_error("Run has no valid demo commit identity")
    requires = scenario["requires"]
    if target.get("release") != requires["cortrix_release"] or target.get("release_commit") != requires["cortrix_release_commit"] or target.get("source_revision") != requires["cortrix_source_revision"] or not isinstance(target.get("container_digest"), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", target["container_digest"]):
        raise _acceptance_integrity_error("Run Cortrix source or container identity is invalid")
    if not isinstance(manifest.get("fixture_manifest_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", manifest["fixture_manifest_sha256"]):
        raise _acceptance_integrity_error("Run fixture manifest checksum is invalid")
    if not isinstance(manifest.get("scenario_version"), str) or not manifest["scenario_version"] or not isinstance(manifest.get("assertion_contract_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", manifest["assertion_contract_sha256"]):
        raise _acceptance_integrity_error("Run scenario version or assertion contract identity is invalid")
    execution = scenario["execution_contract"]
    if manifest.get("campaign_id") != execution["campaign_id"] or not isinstance(manifest.get("campaign_slot"), int) or not 1 <= manifest["campaign_slot"] <= int(execution["campaign_attempt_cap"]):
        raise _acceptance_integrity_error("Run campaign identity or slot is invalid")
    provider = manifest.get("provider_identity")
    if not isinstance(provider, dict) or provider.get("provider") != llm.get("provider") or provider.get("model") != llm.get("model") or provider.get("base_url") != llm.get("base_url", "https://api.deepseek.com/v1") or provider.get("local_generative_llm") is not False:
        raise _acceptance_integrity_error("Run provider identity is not accepted")
    cleanup = manifest.get("cleanup")
    if not isinstance(cleanup, dict) or not all(cleanup.get(key) is True for key in ("namespaces_removed", "containers_removed", "ports_released", "runtime_secret_removed")):
        raise _acceptance_integrity_error("Run cleanup receipt is not complete")
    cost = manifest.get("cost")
    if not isinstance(cost, dict) or not isinstance(cost.get("budget_usd"), (int, float)) or cost["budget_usd"] <= 0 or cost.get("within_budget_contract") is not True or cost.get("public_cost_claim_allowed") is not False or cost.get("usage_visibility") not in {"complete", "partial"} or cost.get("model") != llm.get("model"):
        raise _acceptance_integrity_error("Run cost contract is not accepted")
    for name in ("observable_input_tokens", "observable_output_tokens", "observable_call_count_minimum"):
        if not isinstance(cost.get(name), int) or cost[name] < 0:
            raise _acceptance_integrity_error("Run observable usage fields are invalid")
    minimum_call_count = evidence.get("minimum_external_call_count")
    if not isinstance(minimum_call_count, int) or cost["observable_call_count_minimum"] < minimum_call_count:
        raise _acceptance_integrity_error("Run does not prove the minimum external call count")
    if not isinstance(cost.get("pricing_snapshot"), dict):
        raise _acceptance_integrity_error("Run cost contract has no pricing snapshot")
    pricing = cost["pricing_snapshot"]
    if pricing.get("official_url") != "https://api-docs.deepseek.com/quick_start/pricing" or pricing.get("model") != llm.get("model") or pricing.get("currency") != "USD" or not pricing.get("observed_at"):
        raise _acceptance_integrity_error("Run pricing snapshot identity is invalid")
    expected_outputs = {
        "run_a": (evidence.get("run_a_path"), True),
        "run_b": (evidence.get("run_b_path"), True),
        "resolver": (evidence.get("resolver_path"), True),
    }
    for name, (path, passed) in expected_outputs.items():
        output = manifest.get(name)
        if not isinstance(output, dict) or output.get("path") != path or output.get("pass") is not passed:
            raise _acceptance_integrity_error(f"Run {name} output contract is invalid")
    run_b = manifest["run_b"]
    retrieval = scenario["retrieval_contract"]
    if run_b.get("serial_query_count") != evidence.get("serial_query_count") or run_b.get("query_granularity") != retrieval["query_granularity"] or run_b.get("document_summary_role") != retrieval["document_summary_role"]:
        raise _acceptance_integrity_error("Run B does not record the two-query chunk-only retrieval contract")
    gaps = manifest.get("disclosed_gaps")
    if not isinstance(gaps, list) or not gaps or not all(isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("note"), str) for item in gaps):
        raise _acceptance_integrity_error("Run disclosed gaps are missing or malformed")
    if not isinstance(manifest.get("claim_boundary"), str) or not manifest["claim_boundary"].strip():
        raise _acceptance_integrity_error("Run claim boundary is missing")
    return demo_commit


def validate_layered_resolver_contract(resolver: dict[str, Any], frozen_assertions: dict[str, Any]) -> None:
    assertions = resolver.get("assertions")
    layers = resolver.get("layers")
    if resolver.get("schema_version") != 2 or resolver.get("pass") is not True or not isinstance(assertions, dict) or not all(assertions.get(name) is True for name in LAYERED_RESOLVER_ASSERTIONS):
        raise _acceptance_integrity_error("Resolver does not satisfy the layered-ranking assertions")
    if not isinstance(layers, dict):
        raise _acceptance_integrity_error("Resolver layered-ranking evidence is missing")
    bge = layers.get("bge_cross_encoder")
    final = layers.get("deepseek_listwise_final")
    policy = layers.get("application_lifecycle_policy")
    leader = bge.get("leader") if isinstance(bge, dict) else None
    top_result = final.get("top_result") if isinstance(final, dict) else None
    if not isinstance(leader, dict) or not isinstance(leader.get("document_id"), str) or not isinstance(leader.get("bge_rerank_score"), (int, float)):
        raise _acceptance_integrity_error("Resolver BGE layer does not expose an observable leader")
    if not isinstance(top_result, dict) or top_result.get("document_id") != frozen_assertions.get("run_b_final_top_document_id") or top_result.get("lifecycle_status") != frozen_assertions.get("run_b_final_top_document_status"):
        raise _acceptance_integrity_error("Resolver final layer does not match the frozen assertion contract")
    if not isinstance(policy, dict) or policy.get("action") != frozen_assertions.get("resolver_action"):
        raise _acceptance_integrity_error("Resolver lifecycle action does not match the frozen assertion contract")
    decision = resolver.get("decision")
    if not isinstance(decision, dict) or decision.get("selected_document_id") != frozen_assertions.get("resolver_selected_document_id") or decision.get("selected_field") != frozen_assertions.get("resolver_selected_field"):
        raise _acceptance_integrity_error("Resolver decision does not match the frozen current-document contract")


def validate_run_a_contract(run_a: dict[str, Any], frozen_assertions: dict[str, Any]) -> None:
    assertions = run_a.get("assertions")
    required = {"expected_dense_document_is_top1", "required_current_document_is_present", "strict_dense_top1", "exact_cosine_without_ann", "lifecycle_not_used_in_ranking"}
    if run_a.get("schema_version") != 1 or run_a.get("pass") is not True or not isinstance(assertions, dict) or not all(assertions.get(name) is True for name in required):
        raise _acceptance_integrity_error("Run A does not satisfy the layered dense-baseline assertions")
    if run_a.get("top1") != frozen_assertions.get("run_a_dense_cosine_top_document_id"):
        raise _acceptance_integrity_error("Run A top result does not match the frozen assertion contract")
    ranking = run_a.get("ranking")
    if not isinstance(ranking, list) or not any(isinstance(item, dict) and item.get("document_id") == frozen_assertions.get("run_a_required_current_document_id") and item.get("lifecycle_status") == frozen_assertions.get("run_a_required_current_document_status") for item in ranking):
        raise _acceptance_integrity_error("Run A does not contain the frozen current-document identity")


def validate_run_b_retrieval_contract(run_b: dict[str, Any]) -> None:
    attempts = run_b.get("query_attempts")
    if run_b.get("query_granularity") != "chunk" or run_b.get("document_summary_role") != "ingestion_evidence_only":
        raise _acceptance_integrity_error("Run B does not preserve the chunk-only retrieval contract")
    checks = [item.get("checks") for item in attempts if isinstance(item, dict)] if isinstance(attempts, list) else []
    if not isinstance(attempts, list) or len(attempts) != 2 or len(checks) != 2 or any(not isinstance(item, dict) or item.get("chunk_only_result_identity") is not True for item in checks):
        raise _acceptance_integrity_error("Run B does not prove two chunk-only result identity checks")


def validate_candidate(root: Path, run_id: str, scenario_id: str | None = None) -> dict[str, Any]:
    resolved_id = resolve_scenario_id(root, scenario_id)
    validate_run_id(root, resolved_id, run_id)
    scenario = load_scenario(root, resolved_id)
    validation = load_validation_contract(root, resolved_id)
    require_reviewed_retrieval_contract(scenario, validation)
    assertion_path = assertion_contract_path(root, resolved_id)
    frozen_assertions = load_assertion_contract(root, resolved_id)["frozen"]
    source = candidate_root(root, run_id)
    for relative in REQUIRED_CANDIDATE_FILES:
        if not (source / relative).is_file():
            raise _acceptance_integrity_error(f"Candidate evidence is missing {relative}")
    manifest = require_object(read_json(source / "run-manifest.json"), "Candidate run manifest")
    if manifest.get("run_id") != run_id or manifest.get("scenario_id") != resolved_id:
        raise _acceptance_integrity_error("Candidate manifest identity is inconsistent")
    if manifest.get("state") != "candidate":
        raise _acceptance_integrity_error("Only a candidate run can enter human acceptance")
    if manifest.get("screenshot_eligible") is not False or manifest.get("human_review_required") is not True:
        raise _acceptance_integrity_error("Candidate manifest bypasses the human-review screenshot gate")
    demo_commit = validate_manifest_contract(root, resolved_id, manifest)
    if manifest.get("scenario_version") != scenario.get("scenario_version") or manifest.get("assertion_contract_sha256") != sha256_file(assertion_path):
        raise _acceptance_integrity_error("Candidate scenario version or assertion contract does not match the tracked scenario")
    fixture_manifest = scenario_root(root, resolved_id) / "fixtures" / "manifest.json"
    if sha256_file(fixture_manifest) != manifest.get("fixture_manifest_sha256"):
        raise _acceptance_integrity_error("Candidate fixture manifest checksum does not match the tracked fixture")
    target = require_object(manifest.get("target_identity"), "Candidate target identity")
    source_manifest = require_object(read_json(source / "source-manifest.json"), "Candidate source manifest")
    source_identity = require_object(source_manifest.get("source"), "Candidate source identity")
    expected_source = {
        "cortrix_release": target.get("release"),
        "cortrix_release_commit": target.get("release_commit"),
        "cortrix_source_revision": target.get("source_revision"),
        "container_digest": target.get("container_digest"),
        "demo_commit": demo_commit,
        "demo_branch": "main",
        "demo_working_tree": "clean",
    }
    if source_manifest.get("run_id") != run_id or source_manifest.get("campaign_id") != manifest.get("campaign_id") or source_manifest.get("attempt") != manifest.get("campaign_slot") or source_manifest.get("scenario_version") != scenario.get("scenario_version") or source_manifest.get("assertion_contract_sha256") != manifest.get("assertion_contract_sha256") or any(source_identity.get(key) != value for key, value in expected_source.items()):
        raise _acceptance_integrity_error("Candidate source manifest does not match the run target identity")
    if source_manifest.get("provider") != manifest.get("provider_identity") or source_manifest.get("private_source_paths_recorded") is not False or source_manifest.get("secret_recorded") is not False:
        raise _acceptance_integrity_error("Candidate source manifest provider or safety boundary is invalid")
    smoke = require_object(read_json(source / "contract-smoke.json"), "Candidate contract smoke")
    provider_identity = manifest["provider_identity"]
    if smoke.get("provider") != provider_identity["provider"] or smoke.get("model") != provider_identity["model"] or smoke.get("call_count") != 1 or smoke.get("response_content_recorded") is not False:
        raise _acceptance_integrity_error("Candidate contract smoke identity is invalid")
    runtime = require_object(read_json(source / "runtime.json"), "Candidate runtime identity")
    runtime_llm = runtime.get("llm")
    if runtime.get("run_id") != run_id or not isinstance(runtime_llm, dict) or runtime_llm.get("provider") != provider_identity["provider"] or runtime_llm.get("model") != provider_identity["model"] or runtime_llm.get("local_generative_llm") is not False or runtime_llm.get("secret_persisted_in_evidence") is not False:
        raise _acceptance_integrity_error("Candidate runtime provider or secret boundary is invalid")
    models = require_object(read_json(source / "model-checksums.json"), "Candidate model checksums")
    cleanup_receipt = require_object(read_json(source / "cleanup-receipt.json"), "Candidate cleanup receipt")
    run_a = require_object(read_json(source / "run-a" / "pgvector-result.json"), "Candidate Run A result")
    run_b = require_object(read_json(source / "run-b" / "summary.json"), "Candidate Run B summary")
    resolver_one = require_object(read_json(source / "run-b" / "resolver-01.json"), "Candidate resolver result one")
    resolver_two = require_object(read_json(source / "run-b" / "resolver-02.json"), "Candidate resolver result two")
    validate_run_a_contract(run_a, frozen_assertions)
    validate_layered_resolver_contract(resolver_one, frozen_assertions)
    validate_layered_resolver_contract(resolver_two, frozen_assertions)
    validate_run_b_retrieval_contract(run_b)
    if models.get("all_match") is not True or cleanup_receipt.get("run_id") != run_id or any(cleanup_receipt.get(key) != value for key, value in manifest["cleanup"].items() if key != "path"):
        raise _acceptance_integrity_error("Candidate model or cleanup evidence does not match the manifest")
    if run_a.get("pass") is not True or run_b.get("pass") is not True or any(item.get("run_id") != run_id or item.get("pass") is not True for item in (resolver_one, resolver_two)):
        raise _acceptance_integrity_error("Candidate Run A, Run B, or resolver evidence is invalid")
    return manifest


def copy_json(source: Path, destination: Path) -> None:
    write_json(destination, read_json(source))


def append_accepted_state(source: Path, destination: Path) -> None:
    history = require_object(read_json(source), "Candidate state history")
    transitions = history.get("transitions")
    if not isinstance(transitions, list) or not all(isinstance(item, dict) for item in transitions) or [item.get("state") for item in transitions] != ["created", "running", "candidate"]:
        raise _acceptance_integrity_error("Candidate state history is not created -> running -> candidate")
    transitions.append({"state": "accepted", "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(), "detail": "secondscott_clean_room_passed"})
    write_json(destination, history)


def refresh_checksums(destination: Path) -> dict[str, Any]:
    files = []
    for path in sorted(destination.rglob("*")):
        if path.is_symlink():
            raise _acceptance_integrity_error("Accepted evidence must not contain symbolic links")
        if path.is_file() and path.name != "checksums.json":
            files.append({"path": path.relative_to(destination).as_posix(), "sha256": sha256_file(path)})
    result = {"schema_version": 1, "run_id": destination.name, "files": files}
    write_json(destination / "checksums.json", result)
    return result


def validate_curated_safety(destination: Path) -> None:
    expected = ALLOWED_CURATED_FILES - {"screenshots/screenshot-manifest.json"}
    actual = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
    if actual != expected:
        raise _acceptance_integrity_error(f"Curated staging contains an unexpected file set: {sorted(actual ^ expected)}")
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise _acceptance_integrity_error("Curated staging contains a symbolic link")
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt"}:
            failures = scan_text(path.read_text(encoding="utf-8"), path.relative_to(destination))
            if failures:
                raise _acceptance_integrity_error("Curated staging failed public-safety validation: " + "; ".join(failures))


def stage_accepted(root: Path, run_id: str, clean_room_review_id: str, *, scenario_id: str | None = None, replace_accepted: bool = False) -> dict[str, Any]:
    resolved_id = resolve_scenario_id(root, scenario_id)
    if not CLEAN_ROOM_REVIEW_PATTERN.fullmatch(clean_room_review_id):
        raise _acceptance_input_error(
            "Clean Room review ID must be a REVIEW identifier",
            next_action="Use a review ID that matches the documented REVIEW identifier format.",
        )
    manifest = validate_candidate(root, run_id, resolved_id)
    checkout = verify_demo_checkout(root)
    demo_commit = manifest["target_identity"]["demo_commit"]
    ancestor = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", demo_commit, checkout["commit"]], capture_output=True, check=False)
    if ancestor.returncode != 0:
        raise _acceptance_integrity_error("Candidate demo commit must be an ancestor of the clean acceptance-tooling commit")
    source = candidate_root(root, run_id)
    destination = accepted_root(root, run_id, resolved_id)
    staging = root / ".runs" / f"{run_id}.accepted-stage"
    if destination.exists():
        raise _acceptance_integrity_error("Accepted evidence destination already exists")
    if staging.exists():
        raise _acceptance_integrity_error("Ignored accepted-evidence staging directory already exists")
    pointer_path = scenario_root(root, resolved_id) / "evidence" / "accepted-run.json"
    if pointer_path.exists() and read_json(pointer_path).get("status") == "accepted" and not replace_accepted:
        raise _acceptance_integrity_error("Accepted-run pointer already names an accepted run; use the separately reviewed replacement gate")
    staging.mkdir(parents=True)
    accepted_at = dt.datetime.now(dt.timezone.utc).isoformat()
    accepted_manifest = dict(manifest)
    accepted_manifest.update(
        {
            "state": "accepted",
            "screenshot_eligible": True,
            "human_review_required": False,
            "post_screenshot_human_review_required": True,
            "acceptance": {
                "method": "secondscott_clean_room",
                "verdict": "pass",
                "accepted_at": accepted_at,
                "demo_commit": demo_commit,
                "acceptance_tooling_commit": checkout["commit"],
                "private_review_reference_recorded": False,
            },
        }
    )
    write_json(staging / "run-manifest.json", accepted_manifest)
    source_identity = require_object(read_json(source / "source-manifest.json"), "Candidate source manifest")
    public_source_identity = require_object(source_identity.get("source"), "Candidate source identity")
    cost = require_object(manifest.get("cost"), "Candidate cost contract")
    pricing_snapshot = require_object(cost.get("pricing_snapshot"), "Candidate pricing snapshot")
    write_json(staging / "target-identity.json", public_source_identity)
    write_json(staging / "pricing-snapshot.json", pricing_snapshot)
    shutil.copyfile(scenario_root(root, resolved_id) / "fixtures" / "manifest.json", staging / "fixture-manifest.json")
    shutil.copyfile(assertion_contract_path(root, resolved_id), staging / "assertion-contract.json")
    copy_json(source / "model-checksums.json", staging / "model-checksums.json")
    copy_json(source / "runtime.json", staging / "runtime.json")
    copy_json(source / "contract-smoke.json", staging / "contract-smoke.json")
    copy_json(source / "cleanup-receipt.json", staging / "cleanup-receipt.json")
    write_json(staging / "assertions.json", manifest["assertions"])
    append_accepted_state(source / "state-history.json", staging / "state-history.json")
    for relative in ("run-a/pgvector-result.json", "run-b/summary.json", "run-b/resolver-01.json", "run-b/resolver-02.json"):
        copy_json(source / relative, staging / relative)
    pointer_prefix = f"../../scenarios/{resolved_id}/evidence/runs/{run_id}"
    pointer = {
        "schema_version": 1,
        "status": "accepted",
        "run_id": run_id,
        "demo_commit": demo_commit,
        "manifest": f"{pointer_prefix}/run-manifest.json",
        "run_a": f"{pointer_prefix}/run-a/pgvector-result.json",
        "resolver": f"{pointer_prefix}/run-b/resolver-01.json",
        "screenshot_manifest": f"{pointer_prefix}/screenshots/screenshot-manifest.json",
    }
    refresh_checksums(staging)
    validate_curated_safety(staging)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(destination)
    write_json(pointer_path, pointer)
    return {"status": "accepted_staged", "run_id": run_id, "destination": destination.relative_to(root).as_posix(), "screenshot_eligible": True, "commit_required": True}


def png_dimensions_from_header(header: bytes) -> tuple[int, int]:
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise _screenshot_input_error("Screenshot is not a valid PNG with an IHDR header")
    width, height = struct.unpack(">II", header[16:24])
    if width < 800 or height < 450:
        raise _screenshot_input_error("Screenshot dimensions are below the 800x450 evidence minimum")
    return width, height


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        signature = stream.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise _screenshot_input_error("Screenshot is not a PNG")
        width: int | None = None
        height: int | None = None
        idat = bytearray()
        first_chunk = True
        saw_iend = False
        while True:
            length_bytes = stream.read(4)
            if len(length_bytes) != 4:
                break
            length = struct.unpack(">I", length_bytes)[0]
            if length > 64 * 1024 * 1024:
                raise _screenshot_input_error("Screenshot contains an oversized PNG chunk")
            chunk_type = stream.read(4)
            data = stream.read(length)
            checksum = stream.read(4)
            if len(chunk_type) != 4 or len(data) != length or len(checksum) != 4:
                raise _screenshot_input_error("Screenshot contains a truncated PNG chunk")
            expected_crc = struct.unpack(">I", checksum)[0]
            if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
                raise _screenshot_input_error("Screenshot PNG chunk checksum is invalid")
            if first_chunk:
                if chunk_type != b"IHDR" or len(data) != 13:
                    raise _screenshot_input_error("Screenshot PNG does not start with IHDR")
                width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
                valid_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
                if bit_depth not in valid_depths.get(color_type, set()) or compression != 0 or filtering != 0 or interlace not in {0, 1}:
                    raise _screenshot_input_error("Screenshot PNG header uses an invalid encoding")
                if width < 800 or height < 450:
                    raise _screenshot_input_error("Screenshot dimensions are below the 800x450 evidence minimum")
            elif chunk_type == b"IHDR":
                raise _screenshot_input_error("Screenshot PNG contains more than one IHDR chunk")
            if chunk_type == b"IDAT":
                idat.extend(data)
            if chunk_type == b"IEND":
                if length != 0 or stream.read(1):
                    raise _screenshot_input_error("Screenshot PNG has an invalid IEND or trailing data")
                saw_iend = True
                break
            first_chunk = False
        if width is None or height is None or not idat or not saw_iend:
            raise _screenshot_input_error("Screenshot PNG is missing required image data")
        try:
            if not zlib.decompress(bytes(idat)):
                raise _screenshot_input_error("Screenshot PNG has empty decoded image data")
        except zlib.error as exc:
            raise _screenshot_input_error("Screenshot PNG image data is invalid") from exc
        return width, height


def record_screenshot(root: Path, run_id: str, source_file: Path, route: str, evidence_path: str, *, scenario_id: str | None = None) -> dict[str, Any]:
    resolved_id = resolve_scenario_id(root, scenario_id)
    validate_run_id(root, resolved_id, run_id)
    if not SCREENSHOT_PATTERN.fullmatch(source_file.name):
        raise _acceptance_input_error(
            "Screenshot filename is not public-safe",
            next_action="Use an ASCII PNG filename that follows the documented public safety pattern.",
        )
    if route != "/packages/viewer/index.html":
        raise _acceptance_input_error(
            "Screenshot route must be the accepted evidence viewer",
            next_action="Use /packages/viewer/index.html as the screenshot route.",
        )
    destination = accepted_root(root, run_id, resolved_id)
    destination_resolved = destination.resolve()
    manifest = require_object(read_json(destination / "run-manifest.json"), "Accepted run manifest")
    if manifest.get("state") != "accepted" or manifest.get("screenshot_eligible") is not True:
        raise _acceptance_integrity_error("Only human-accepted evidence is screenshot-eligible")
    evidence_source = destination / evidence_path
    if not evidence_source.is_file() or destination_resolved not in evidence_source.resolve().parents:
        raise _acceptance_input_error(
            "Screenshot evidence path is outside the accepted run",
            next_action="Select an existing evidence path inside the accepted run.",
        )
    width, height = png_dimensions(source_file)
    screenshots = destination / "screenshots"
    screenshots.mkdir(exist_ok=True)
    target = screenshots / source_file.name
    if target.exists():
        raise _acceptance_integrity_error("Screenshot destination already exists")
    manifest_path = screenshots / "screenshot-manifest.json"
    target_identity = require_object(manifest.get("target_identity"), "Accepted target identity")
    demo_commit = target_identity.get("demo_commit")
    if not isinstance(demo_commit, str) or not COMMIT_PATTERN.fullmatch(demo_commit):
        raise _acceptance_integrity_error("Accepted evidence demo commit is invalid")
    screenshot_manifest = require_object(read_json(manifest_path), "Screenshot manifest") if manifest_path.exists() else {"schema_version": 1, "run_id": run_id, "accepted_commit": demo_commit, "screenshots": []}
    screenshots_value = screenshot_manifest.get("screenshots")
    if screenshot_manifest.get("run_id") != run_id or screenshot_manifest.get("accepted_commit") != demo_commit or not isinstance(screenshots_value, list):
        raise _acceptance_integrity_error("Screenshot manifest identity or list is invalid")
    shutil.copy2(source_file, target)
    screenshots_value.append(
        {
            "file": f"screenshots/{target.name}",
            "route": route,
            "evidence_path": evidence_path,
            "sha256": sha256_file(target),
            "width": width,
            "height": height,
            "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    write_json(manifest_path, screenshot_manifest)
    refresh_checksums(destination)
    return screenshots_value[-1]


def verify_checksum_manifest(destination: Path) -> None:
    checksums = read_json(destination / "checksums.json")
    records = checksums.get("files")
    if not isinstance(records, list) or not records:
        raise _acceptance_integrity_error("Accepted evidence checksum manifest is empty")
    if not all(isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str) for item in records):
        raise _acceptance_integrity_error("Accepted evidence checksum records are malformed")
    expected = {item["path"]: item["sha256"] for item in records}
    if len(expected) != len(records):
        raise _acceptance_integrity_error("Accepted evidence checksum manifest contains duplicate paths")
    actual = {path.relative_to(destination).as_posix(): sha256_file(path) for path in destination.rglob("*") if path.is_file() and path.name != "checksums.json"}
    if expected != actual:
        raise _acceptance_integrity_error("Accepted evidence checksums do not match the curated files")


def verify_accepted(root: Path, run_id: str, *, scenario_id: str | None = None) -> dict[str, Any]:
    resolved_id = resolve_scenario_id(root, scenario_id)
    validate_run_id(root, resolved_id, run_id)
    scenario = load_scenario(root, resolved_id)
    validation = load_validation_contract(root, resolved_id)
    require_reviewed_retrieval_contract(scenario, validation)
    tracked_assertion_path = assertion_contract_path(root, resolved_id)
    frozen_assertions = load_assertion_contract(root, resolved_id)["frozen"]
    destination = accepted_root(root, run_id, resolved_id)
    pointer = read_json(scenario_root(root, resolved_id) / "evidence" / "accepted-run.json")
    manifest = read_json(destination / "run-manifest.json")
    resolver = read_json(destination / "run-b" / "resolver-01.json")
    if not all(isinstance(value, dict) for value in (pointer, manifest, resolver)):
        raise _acceptance_integrity_error("Accepted pointer, manifest, and resolver must be JSON objects")
    validate_layered_resolver_contract(resolver, frozen_assertions)
    pointer_prefix = f"../../scenarios/{resolved_id}/evidence/runs/{run_id}"
    expected_pointer = {
        "manifest": f"{pointer_prefix}/run-manifest.json",
        "run_a": f"{pointer_prefix}/run-a/pgvector-result.json",
        "resolver": f"{pointer_prefix}/run-b/resolver-01.json",
        "screenshot_manifest": f"{pointer_prefix}/screenshots/screenshot-manifest.json",
    }
    if pointer.get("status") != "accepted" or pointer.get("run_id") != run_id or manifest.get("state") != "accepted" or manifest.get("run_id") != run_id or resolver.get("run_id") != run_id:
        raise _acceptance_integrity_error("Accepted pointer, manifest, and resolver identity do not match")
    if any(pointer.get(key) != value for key, value in expected_pointer.items()):
        raise _acceptance_integrity_error("Accepted-run pointer paths do not match the curated run")
    assertions = manifest.get("assertions")
    if not isinstance(assertions, dict) or assertions.get("all_passed") is not True or resolver.get("pass") is not True:
        raise _acceptance_integrity_error("Accepted evidence assertions are not all passing")
    demo_commit = validate_manifest_contract(root, resolved_id, manifest)
    if manifest.get("scenario_version") != scenario.get("scenario_version") or manifest.get("assertion_contract_sha256") != sha256_file(tracked_assertion_path):
        raise _acceptance_integrity_error("Accepted scenario version or assertion contract does not match the tracked scenario")
    target_identity = require_object(manifest.get("target_identity"), "Accepted target identity")
    acceptance = manifest.get("acceptance")
    tooling_commit = acceptance.get("acceptance_tooling_commit") if isinstance(acceptance, dict) else None
    expected_acceptance_method = validation["evidence_contract"]["acceptance_method"]
    if manifest.get("screenshot_eligible") is not True or manifest.get("human_review_required") is not False or manifest.get("post_screenshot_human_review_required") is not True or not isinstance(acceptance, dict) or acceptance.get("method") != expected_acceptance_method or acceptance.get("verdict") != "pass" or acceptance.get("demo_commit") != demo_commit or not isinstance(tooling_commit, str) or not COMMIT_PATTERN.fullmatch(tooling_commit) or acceptance.get("private_review_reference_recorded") is not False:
        raise _acceptance_integrity_error("Accepted manifest does not preserve the Clean Room and post-screenshot Human Review gates")
    if pointer.get("demo_commit") != demo_commit:
        raise _acceptance_integrity_error("Accepted-run pointer commit does not match the run manifest")
    commit_check = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{demo_commit}^{{commit}}"], capture_output=True, check=False)
    if commit_check.returncode != 0:
        raise _acceptance_integrity_error("Accepted evidence demo commit is not present in Git history")
    tooling_commit_check = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{tooling_commit}^{{commit}}"], capture_output=True, check=False)
    if tooling_commit_check.returncode != 0:
        raise _acceptance_integrity_error("Accepted evidence tooling commit is not present in Git history")
    curated_target = require_object(read_json(destination / "target-identity.json"), "Curated target identity")
    expected_target = {
        "cortrix_release": target_identity.get("release"),
        "cortrix_release_commit": target_identity.get("release_commit"),
        "cortrix_source_revision": target_identity.get("source_revision"),
        "container_digest": target_identity.get("container_digest"),
        "demo_commit": demo_commit,
        "demo_branch": "main",
        "demo_working_tree": "clean",
    }
    if any(curated_target.get(key) != value for key, value in expected_target.items()):
        raise _acceptance_integrity_error("Curated target identity does not match the accepted manifest")
    smoke = require_object(read_json(destination / "contract-smoke.json"), "Curated contract smoke")
    runtime = require_object(read_json(destination / "runtime.json"), "Curated runtime identity")
    runtime_llm = runtime.get("llm")
    provider_identity = manifest["provider_identity"]
    if smoke.get("provider") != provider_identity["provider"] or smoke.get("model") != provider_identity["model"] or smoke.get("call_count") != 1 or smoke.get("response_content_recorded") is not False:
        raise _acceptance_integrity_error("Curated contract smoke identity is invalid")
    if runtime.get("run_id") != run_id or not isinstance(runtime_llm, dict) or runtime_llm.get("provider") != provider_identity["provider"] or runtime_llm.get("model") != provider_identity["model"] or runtime_llm.get("local_generative_llm") is not False or runtime_llm.get("secret_persisted_in_evidence") is not False:
        raise _acceptance_integrity_error("Curated runtime provider or secret boundary is invalid")
    pricing = require_object(read_json(destination / "pricing-snapshot.json"), "Curated pricing snapshot")
    fixture = destination / "fixture-manifest.json"
    curated_assertion_path = destination / "assertion-contract.json"
    models = require_object(read_json(destination / "model-checksums.json"), "Curated model checksums")
    curated_assertions = require_object(read_json(destination / "assertions.json"), "Curated assertions")
    cleanup_receipt = require_object(read_json(destination / "cleanup-receipt.json"), "Curated cleanup receipt")
    run_a = require_object(read_json(destination / "run-a" / "pgvector-result.json"), "Curated Run A result")
    run_b = require_object(read_json(destination / "run-b" / "summary.json"), "Curated Run B summary")
    resolver_two = require_object(read_json(destination / "run-b" / "resolver-02.json"), "Curated resolver result two")
    validate_run_a_contract(run_a, frozen_assertions)
    validate_layered_resolver_contract(resolver_two, frozen_assertions)
    validate_run_b_retrieval_contract(run_b)
    if pricing != manifest["cost"]["pricing_snapshot"] or sha256_file(fixture) != manifest.get("fixture_manifest_sha256") or sha256_file(curated_assertion_path) != manifest.get("assertion_contract_sha256") or read_json(curated_assertion_path) != read_json(tracked_assertion_path):
        raise _acceptance_integrity_error("Curated pricing, fixture, or assertion contract identity does not match the accepted manifest")
    if models.get("all_match") is not True or curated_assertions != assertions or any(cleanup_receipt.get(key) != value for key, value in manifest["cleanup"].items() if key != "path"):
        raise _acceptance_integrity_error("Curated model, assertion, or cleanup evidence does not match the accepted manifest")
    if run_a.get("pass") is not True or run_b.get("pass") is not True or resolver_two.get("run_id") != run_id or resolver_two.get("pass") is not True:
        raise _acceptance_integrity_error("Curated Run A, Run B, or second resolver evidence is invalid")
    screenshot_manifest = require_object(read_json(destination / "screenshots" / "screenshot-manifest.json"), "Accepted screenshot manifest")
    screenshots = screenshot_manifest.get("screenshots")
    if screenshot_manifest.get("run_id") != run_id or screenshot_manifest.get("accepted_commit") != demo_commit or not isinstance(screenshots, list) or not screenshots:
        raise _acceptance_integrity_error("Accepted screenshot manifest is missing or has the wrong identity")
    for item in screenshots:
        if not isinstance(item, dict):
            raise _acceptance_integrity_error("Accepted screenshot entry must be a JSON object")
        path = destination / str(item.get("file"))
        evidence_source = destination / str(item.get("evidence_path"))
        destination_resolved = destination.resolve()
        if destination_resolved not in path.resolve().parents or destination_resolved not in evidence_source.resolve().parents:
            raise _acceptance_integrity_error("Screenshot file or evidence binding escapes the accepted run")
        if item.get("route") != "/packages/viewer/index.html" or not path.is_file() or not evidence_source.is_file():
            raise _acceptance_integrity_error("Screenshot route or evidence binding is invalid")
        width, height = png_dimensions(path)
        if item.get("sha256") != sha256_file(path) or item.get("width") != width or item.get("height") != height:
            raise _acceptance_integrity_error("Screenshot checksum or dimensions do not match")
    allowed = set(ALLOWED_CURATED_FILES)
    allowed.update(str(item["file"]) for item in screenshots)
    actual_files = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
    if actual_files != allowed:
        raise _acceptance_integrity_error(f"Accepted evidence contains an unexpected file set: {sorted(actual_files ^ allowed)}")
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise _acceptance_integrity_error("Accepted evidence contains a symbolic link")
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt"}:
            failures = scan_text(path.read_text(encoding="utf-8"), path.relative_to(root))
            if failures:
                raise _acceptance_integrity_error("Accepted evidence failed public-safety validation: " + "; ".join(failures))
    verify_checksum_manifest(destination)
    return {"status": "pass", "scenario_id": resolved_id, "run_id": run_id, "demo_commit": demo_commit, "proof_scope": "archive_integrity", "live_reexecution": False, "screenshot_count": len(screenshots), "checksums": "pass", "public_safety": "pass"}
