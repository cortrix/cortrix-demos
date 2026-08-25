from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .acceptance import png_dimensions
from .errors import DemoContractError
from .io import read_json, sha256_file, write_json
from .safety import scan_text
from .scenario import load_assertion_contract, load_scenario, scenario_root


HARNESS_COMPARISON_KIND = "deepseek_harness_cortrix_readonly"
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
REVIEW_PATTERN = re.compile(r"REVIEW-[A-Z0-9][A-Z0-9._-]{7,127}")
SCREENSHOT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.png")
REQUIRED_RUN_FILES = {
    "run-manifest.json",
    "runtime.json",
    "cleanup.json",
    "run-a/evidence.json",
    "run-a/answer-prompt.txt",
    "run-a/answer.json",
    "run-a/usage.json",
    "run-a/resolver.json",
    "run-a/summary.json",
    "run-b/ingestion.json",
    "run-b/tool-session-01.json",
    "run-b/tool-session-02.json",
    "run-b/evidence-01.json",
    "run-b/evidence-02.json",
    "run-b/answer-prompt.txt",
    "run-b/answer.json",
    "run-b/usage.json",
    "run-b/resolver.json",
    "run-b/summary.json",
}


def _failure(message: str) -> DemoContractError:
    return DemoContractError(message, code="CX_DEMO_HARNESS_ACCEPTANCE_INVALID")


def _is_commit_ancestor(root: Path, candidate_commit: str, tooling_commit: str) -> bool:
    completed = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", candidate_commit, tooling_commit], check=False)
    return completed.returncode == 0


def _scenario(root: Path, scenario_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    scenario = load_scenario(root, scenario_id)
    if scenario.get("integration_kind") != HARNESS_COMPARISON_KIND:
        raise _failure("Harness acceptance supports only registered Harness comparison scenarios")
    assertions = load_assertion_contract(root, scenario_id)["frozen"]
    return scenario_root(root, scenario_id), scenario, assertions


def _run_pattern(scenario_id: str) -> re.Pattern[str]:
    return re.compile(rf"{re.escape(scenario_id)}-[0-9]{{8}}T[0-9]{{6}}Z(?:-retry)?")


def _require_relative_file(run_dir: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise _failure(f"Harness manifest is missing {label}")
    path = (run_dir / relative).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise _failure(f"Harness {label} escapes the run directory") from exc
    if not path.is_file() or path.is_symlink():
        raise _failure(f"Harness {label} is missing or is a symbolic link")
    return path


def _validate_manifest_shape(manifest: dict[str, Any], scenario_id: str, run_id: str, *, state: str, budget_usd: float, observable_calls: int) -> None:
    required = {
        "schema_version", "scenario_id", "run_id", "state", "source_identity", "comparison", "provider", "usage",
        "pricing_snapshot", "run_a", "run_b", "resolver", "cleanup", "screenshot_eligible", "human_review_required",
    }
    if manifest.get("schema_version") != 1 or manifest.get("scenario_id") != scenario_id or manifest.get("run_id") != run_id or manifest.get("state") != state:
        raise _failure("Harness run manifest identity or state is invalid")
    if not required.issubset(manifest):
        raise _failure("Harness run manifest is missing required fields")
    source = manifest.get("source_identity")
    if not isinstance(source, dict) or any(not isinstance(source.get(key), str) or not COMMIT_PATTERN.fullmatch(source[key]) for key in ("demo_commit", "plugin_commit", "harness_commit", "cortrix_commit")):
        raise _failure("Harness source identity is invalid")
    comparison = manifest.get("comparison")
    if not isinstance(comparison, dict) or any(comparison.get(key) is not True for key in ("same_harness", "same_model", "same_prompt", "same_corpus", "same_non_cortrix_tools")) or comparison.get("only_independent_variable") != "cortrix_bundle_loaded":
        raise _failure("Harness comparison controls are invalid")
    provider = manifest.get("provider")
    if not isinstance(provider, dict) or provider.get("provider") != "deepseek" or provider.get("model") != "deepseek-v4-flash" or provider.get("local_generative_llm") is not False or provider.get("fallback_used") is not False or provider.get("secret_value_recorded") is not False:
        raise _failure("Harness provider identity or safety boundary is invalid")
    usage = manifest.get("usage")
    if not isinstance(usage, dict) or usage.get("observable_calls") != observable_calls or usage.get("budget_usd") != budget_usd or usage.get("observable_cost_usd", budget_usd + 1) > budget_usd or usage.get("reviewed_bound_usd", budget_usd + 1) > budget_usd:
        raise _failure("Harness usage or cost contract is invalid")
    if state == "candidate" and (manifest.get("screenshot_eligible") is not False or manifest.get("human_review_required") is not True or manifest.get("acceptance") is not None):
        raise _failure("Harness candidate bypasses the acceptance and screenshot gates")
    if state == "accepted":
        acceptance = manifest.get("acceptance")
        if manifest.get("screenshot_eligible") is not True or manifest.get("human_review_required") is not False or not isinstance(acceptance, dict) or acceptance.get("method") != "independent_clean_room" or acceptance.get("verdict") != "pass":
            raise _failure("Harness accepted run does not preserve the independent Clean Room gate")


def _validate_checksums(run_dir: Path, *, require_review: bool) -> None:
    checksums = read_json(run_dir / "checksums.json")
    files = checksums.get("files")
    if checksums.get("schema_version") != 1 or checksums.get("run_id") != run_dir.name or not isinstance(files, list):
        raise _failure("Harness checksum manifest identity is invalid")
    expected: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise _failure("Harness checksum entry is invalid")
        if item["path"] in expected:
            raise _failure("Harness checksum manifest contains a duplicate path")
        expected[item["path"]] = item["sha256"]
    actual = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != "checksums.json" and "harness-home" not in path.parts
    }
    if require_review:
        actual.add("clean-room-review.json")
    if set(expected) != actual:
        raise _failure("Harness checksum manifest does not cover the complete curated run")
    for relative, digest in expected.items():
        path = _require_relative_file(run_dir, relative, "checksummed evidence")
        if sha256_file(path) != digest:
            raise _failure("Harness evidence checksum mismatch")


def refresh_harness_checksums(run_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(run_dir.rglob("*")):
        if "harness-home" in path.relative_to(run_dir).parts:
            continue
        if path.is_symlink():
            raise _failure("Harness evidence must not contain symbolic links")
        if path.is_file() and path.name != "checksums.json":
            files.append({"path": path.relative_to(run_dir).as_posix(), "sha256": sha256_file(path)})
    result = {"schema_version": 1, "run_id": run_dir.name, "files": files}
    write_json(run_dir / "checksums.json", result)
    return result


def _validate_safety(run_dir: Path, repository_root: Path | None = None) -> None:
    for path in run_dir.rglob("*"):
        # Harness homes are raw provider runtime state. They are deliberately
        # excluded from curated checksums and accepted evidence, so public
        # safety validation must apply the same boundary before inspecting
        # package-manager symlinks or runtime-only text.
        if "harness-home" in path.relative_to(run_dir).parts:
            continue
        if path.is_symlink():
            raise _failure("Harness evidence contains a symbolic link")
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt"}:
            relative = path.relative_to(repository_root) if repository_root is not None else path.relative_to(run_dir)
            failures = scan_text(path.read_text(encoding="utf-8"), relative)
            if failures:
                raise _failure("Harness evidence failed public safety: " + "; ".join(failures))


def _usage_contract(scenario_dir: Path) -> tuple[float, int]:
    profile = read_json(scenario_dir / "profiles" / "full-stack.json")
    budget = profile.get("budget_usd")
    calls = profile.get("expected_campaign_calls")
    if not isinstance(budget, (int, float)) or not isinstance(calls, int):
        raise _failure("Harness scenario has no accepted usage contract")
    return float(budget), calls


def _validate_position_variants(run_dir: Path, scenario_dir: Path, scenario: dict[str, Any], assertions: dict[str, Any], manifest: dict[str, Any]) -> None:
    fixtures = scenario.get("fixtures")
    variants_path = fixtures.get("position_variants") if isinstance(fixtures, dict) else None
    manifest_entry = manifest.get("position_variants")
    if variants_path is None:
        if manifest_entry is not None:
            raise _failure("Harness manifest unexpectedly contains position variants")
        return
    if not isinstance(manifest_entry, dict) or manifest_entry.get("pass") is not True:
        raise _failure("Harness position variant aggregate is missing or failed")
    summary_path = _require_relative_file(run_dir, manifest_entry.get("path"), "position variant aggregate")
    if sha256_file(summary_path) != manifest_entry.get("sha256"):
        raise _failure("Harness position variant aggregate checksum is invalid")
    frozen = read_json(scenario_dir / variants_path)
    expected_variants = [item.get("id") for item in frozen.get("variants", []) if isinstance(item, dict)]
    summary = read_json(summary_path)
    rows = summary.get("variants")
    if expected_variants != ["front", "middle", "end"] or summary.get("all_variants_pass") is not True or not isinstance(rows, list) or [row.get("variant") for row in rows if isinstance(row, dict)] != expected_variants:
        raise _failure("Harness position variant aggregate identity is invalid")
    frozen_by_id = {item["id"]: item for item in frozen["variants"]}
    for row in rows:
        variant = row["variant"]
        if any(row.get(key) is not True for key in ("run_a_pass", "run_b_pass", "authority_pass", "resolver_pass", "cleanup_pass")):
            raise _failure(f"Harness position variant {variant} did not pass")
        comparison = run_dir / "position-variants" / variant
        for relative in REQUIRED_RUN_FILES - {"run-manifest.json", "runtime.json"}:
            _require_relative_file(comparison, relative, f"position variant {variant} {relative}")
        run_a = read_json(comparison / "run-a" / "summary.json")
        run_b = read_json(comparison / "run-b" / "summary.json")
        resolver = read_json(comparison / "run-b" / "resolver.json")
        evidence = read_json(comparison / "run-b" / "evidence-01.json")
        if run_a.get("position_variant") != variant or run_a.get("authority_pass") is not False or run_b.get("position_variant") != variant or run_b.get("authority_pass") is not True or run_b.get("serial_source_order_identical") is not True:
            raise _failure(f"Harness position variant {variant} comparison is invalid")
        if resolver.get("resolver_selected_document_id") != assertions["resolver_selected_document_id"] or resolver.get("pass") is not True:
            raise _failure(f"Harness position variant {variant} resolver is invalid")
        if evidence.get("position_variant") != variant:
            raise _failure(f"Harness position variant {variant} evidence identity is invalid")
        event_source = next((item for item in evidence.get("evidence", []) if item.get("document_id") == frozen.get("document_id")), None)
        if not isinstance(event_source, dict) or event_source.get("fixture_sha256") != frozen_by_id[variant]["sha256"]:
            raise _failure(f"Harness position variant {variant} event source hash is invalid")


def validate_harness_candidate(root: Path, scenario_id: str, run_id: str, *, require_review: bool = False) -> dict[str, Any]:
    scenario_dir, scenario, assertions = _scenario(root, scenario_id)
    if not _run_pattern(scenario_id).fullmatch(run_id):
        raise _failure("Harness run ID does not match the scenario contract")
    run_dir = root / ".runs" / run_id
    if not run_dir.is_dir():
        raise _failure("Harness candidate run directory does not exist")
    for relative in REQUIRED_RUN_FILES | {"checksums.json"}:
        _require_relative_file(run_dir, relative, relative)
    manifest = read_json(run_dir / "run-manifest.json")
    budget_usd, observable_calls = _usage_contract(scenario_dir)
    _validate_manifest_shape(manifest, scenario_id, run_id, state="candidate", budget_usd=budget_usd, observable_calls=observable_calls)
    source = manifest["source_identity"]
    expected = scenario["requires"]
    if source.get("harness_commit") != expected["deepseek_harness_commit"] or source.get("cortrix_commit") != expected["cortrix_source_revision"]:
        raise _failure("Harness candidate source identity differs from the frozen scenario")
    if source.get("fixture_manifest_sha256") != sha256_file(scenario_dir / "fixtures" / "manifest.json") or source.get("assertion_contract_sha256") != sha256_file(scenario_dir / "expected" / "assertions.json"):
        raise _failure("Harness candidate fixture or assertion identity has drifted")
    run_a_summary = read_json(run_dir / "run-a" / "summary.json")
    run_a_resolver = read_json(run_dir / "run-a" / "resolver.json")
    run_b_summary = read_json(run_dir / "run-b" / "summary.json")
    run_b_resolver = read_json(run_dir / "run-b" / "resolver.json")
    if run_a_summary.get("pass") is not True or run_a_summary.get("authority_pass") is not False or run_a_summary.get("expected_outcome_observed") is not True:
        raise _failure("Harness Run A did not preserve the expected negative control")
    if run_a_resolver.get("pass") is not True or run_a_resolver.get("authority_pass") is not False:
        raise _failure("Harness Run A resolver result is invalid")
    if run_b_summary.get("pass") is not True or run_b_summary.get("authority_pass") is not True or run_b_summary.get("expected_outcome_observed") is not True or run_b_summary.get("serial_query_count") != 2 or run_b_summary.get("serial_source_order_identical") is not True:
        raise _failure("Harness Run B did not preserve the two-query passing contract")
    if run_b_resolver.get("pass") is not True or run_b_resolver.get("authority_pass") is not True or run_b_resolver.get("resolver_selected_document_id") != assertions["resolver_selected_document_id"]:
        raise _failure("Harness Run B resolver result is invalid")
    _validate_position_variants(run_dir, scenario_dir, scenario, assertions, manifest)
    for section in ("run_a", "run_b", "resolver", "cleanup"):
        entry = manifest.get(section)
        if not isinstance(entry, dict) or entry.get("pass") is not True:
            raise _failure(f"Harness manifest {section} gate did not pass")
        path = _require_relative_file(run_dir, entry.get("path"), section)
        if sha256_file(path) != entry.get("sha256"):
            raise _failure(f"Harness manifest {section} checksum is invalid")
    runtime = read_json(run_dir / "runtime.json")
    models = runtime.get("model_checksums")
    if runtime.get("source_revision") != expected["cortrix_source_revision"] or runtime.get("downloads") != 0 or runtime.get("builds") != 0 or runtime.get("model_cache_action") != "reused" or not isinstance(models, dict) or models.get("all_match") is not True:
        raise _failure("Harness runtime source, model cache, download, or build evidence is invalid")
    cleanup = read_json(run_dir / "cleanup.json")
    if cleanup.get("removed_or_absent") is not True or cleanup.get("containers_absent") is not True or cleanup.get("runtime_secret_materialized") is not False:
        raise _failure("Harness cleanup receipt is incomplete")
    if require_review:
        review = read_json(run_dir / "clean-room-review.json")
        if review.get("scenario_id") != scenario_id or review.get("run_id") != run_id or review.get("verdict") != "pass" or review.get("clean_clone") is not True or review.get("manual_runbooks_verified") is not True or review.get("secret_scan_pass") is not True or review.get("cleanup_pass") is not True or not REVIEW_PATTERN.fullmatch(str(review.get("review_id", ""))):
            raise _failure("Harness independent Clean Room review is invalid")
    _validate_checksums(run_dir, require_review=require_review)
    _validate_safety(run_dir)
    return manifest


def record_harness_clean_room_pass(root: Path, scenario_id: str, run_id: str, review_id: str) -> dict[str, Any]:
    if not REVIEW_PATTERN.fullmatch(review_id):
        raise _failure("Clean Room review ID does not match the public REVIEW identifier contract")
    manifest = validate_harness_candidate(root, scenario_id, run_id)
    branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(root), "status", "--short", "--untracked-files=all"], check=True, capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if branch != "main" or status:
        raise _failure("Clean Room review must be recorded from a clean main checkout")
    candidate_commit = manifest["source_identity"]["demo_commit"]
    if not _is_commit_ancestor(root, candidate_commit, head):
        raise _failure("Harness candidate commit is not an ancestor of the Clean Room tooling commit")
    run_dir = root / ".runs" / run_id
    review = {
        "schema_version": 1,
        "review_id": review_id,
        "method": "independent_clean_room",
        "reviewer_context": "fresh_agent_clean_clone",
        "scenario_id": scenario_id,
        "run_id": run_id,
        "verdict": "pass",
        "clean_clone": True,
        "safe_bootstrap_pass": True,
        "static_validation_pass": True,
        "manual_runbooks_verified": True,
        "live_candidate_pass": True,
        "secret_scan_pass": True,
        "cleanup_pass": True,
        "tracked_worktree_clean": True,
        "private_review_reference_recorded": False,
    }
    write_json(run_dir / "clean-room-review.json", review)
    refresh_harness_checksums(run_dir)
    validate_harness_candidate(root, scenario_id, run_id, require_review=True)
    return {"status": "pass", "scenario_id": scenario_id, "run_id": run_id, "review_id": review_id, "external_calls": 0}


def _copy_curated_candidate(source: Path, staging: Path) -> None:
    checksums = read_json(source / "checksums.json")
    for entry in checksums["files"]:
        relative = entry["path"]
        source_file = _require_relative_file(source, relative, "curated candidate file")
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)


def stage_harness_accepted(root: Path, scenario_id: str, run_id: str) -> dict[str, Any]:
    scenario_dir, _, _ = _scenario(root, scenario_id)
    manifest = validate_harness_candidate(root, scenario_id, run_id, require_review=True)
    branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(root), "status", "--short", "--untracked-files=all"], check=True, capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if branch != "main" or status:
        raise _failure("Harness acceptance requires a clean main checkout")
    candidate_commit = manifest["source_identity"]["demo_commit"]
    ancestor = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", candidate_commit, head], check=False)
    if ancestor.returncode != 0:
        raise _failure("Harness candidate commit is not an ancestor of the acceptance tooling commit")
    source = root / ".runs" / run_id
    destination = scenario_dir / "evidence" / "runs" / run_id
    staging = root / ".runs" / f"{run_id}.accepted-stage"
    if destination.exists() or staging.exists():
        raise _failure("Harness accepted evidence destination already exists")
    staging.mkdir(parents=True)
    _copy_curated_candidate(source, staging)
    review = read_json(staging / "clean-room-review.json")
    accepted_manifest = read_json(staging / "run-manifest.json")
    accepted_manifest.update(
        {
            "state": "accepted",
            "screenshot_eligible": True,
            "human_review_required": False,
            "post_screenshot_human_review_required": True,
            "acceptance": {
                "method": "independent_clean_room",
                "review_id": review["review_id"],
                "verdict": "pass",
                "accepted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "acceptance_tooling_commit": head,
                "private_review_reference_recorded": False,
            },
            "screenshots": [],
        }
    )
    write_json(staging / "run-manifest.json", accepted_manifest)
    refresh_harness_checksums(staging)
    _validate_safety(staging)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(destination)
    prefix = f"../../scenarios/{scenario_id}/evidence/runs/{run_id}"
    pointer = {
        "schema_version": 1,
        "scenario_id": scenario_id,
        "status": "accepted",
        "run_id": run_id,
        "demo_commit": candidate_commit,
        "manifest": f"{prefix}/run-manifest.json",
        "run_a_summary": f"{prefix}/run-a/summary.json",
        "run_a_answer": f"{prefix}/run-a/answer.json",
        "run_a_resolver": f"{prefix}/run-a/resolver.json",
        "run_b_summary": f"{prefix}/run-b/summary.json",
        "run_b_answer": f"{prefix}/run-b/answer.json",
        "run_b_evidence": f"{prefix}/run-b/evidence-01.json",
        "resolver": f"{prefix}/run-b/resolver.json",
        "cleanup": f"{prefix}/cleanup.json",
        "screenshot_manifest": f"{prefix}/screenshots/screenshot-manifest.json",
    }
    write_json(scenario_dir / "evidence" / "accepted-run.json", pointer)
    return {"status": "accepted_staged", "scenario_id": scenario_id, "run_id": run_id, "destination": destination.relative_to(root).as_posix(), "screenshot_eligible": True, "commit_required": True}


def record_harness_screenshot(root: Path, scenario_id: str, run_id: str, source_file: Path, route: str, evidence_path: str, *, replace: bool = False) -> dict[str, Any]:
    scenario_dir, _, _ = _scenario(root, scenario_id)
    expected_route = f"/packages/viewer/harness.html?scenario={scenario_id}"
    if route != expected_route:
        raise _failure("Harness screenshot route does not match the accepted scenario viewer")
    if not SCREENSHOT_PATTERN.fullmatch(source_file.name):
        raise _failure("Harness screenshot filename is not public safe")
    destination = scenario_dir / "evidence" / "runs" / run_id
    manifest = read_json(destination / "run-manifest.json")
    budget_usd, observable_calls = _usage_contract(scenario_dir)
    _validate_manifest_shape(manifest, scenario_id, run_id, state="accepted", budget_usd=budget_usd, observable_calls=observable_calls)
    evidence = _require_relative_file(destination, evidence_path, "screenshot evidence path")
    width, height = png_dimensions(source_file)
    screenshots = destination / "screenshots"
    screenshots.mkdir(exist_ok=True)
    target = screenshots / source_file.name
    if target.exists() and not replace:
        raise _failure("Harness screenshot destination already exists")
    screenshot_manifest_path = screenshots / "screenshot-manifest.json"
    screenshot_manifest = read_json(screenshot_manifest_path) if screenshot_manifest_path.exists() else {"schema_version": 1, "scenario_id": scenario_id, "run_id": run_id, "accepted_commit": manifest["source_identity"]["demo_commit"], "screenshots": []}
    target_name = f"screenshots/{target.name}"
    matching = [index for index, item in enumerate(screenshot_manifest["screenshots"]) if item.get("file") == target_name]
    if replace and (not target.exists() or len(matching) != 1):
        raise _failure("Harness screenshot replacement requires exactly one existing bound screenshot")
    shutil.copyfile(source_file, target)
    entry = {
        "file": target_name,
        "sha256": sha256_file(target),
        "width": width,
        "height": height,
        "route": route,
        "evidence_path": evidence.relative_to(destination).as_posix(),
    }
    if replace:
        screenshot_manifest["screenshots"][matching[0]] = entry
    else:
        screenshot_manifest["screenshots"].append(entry)
    write_json(screenshot_manifest_path, screenshot_manifest)
    manifest["screenshots"] = screenshot_manifest["screenshots"]
    write_json(destination / "run-manifest.json", manifest)
    refresh_harness_checksums(destination)
    _validate_safety(destination, root)
    return {"status": "replaced" if replace else "recorded", "scenario_id": scenario_id, "run_id": run_id, "file": f"screenshots/{target.name}", "width": width, "height": height, "sha256": sha256_file(target)}


def verify_harness_accepted(root: Path, scenario_id: str, run_id: str | None = None) -> dict[str, Any]:
    scenario_dir, _, _ = _scenario(root, scenario_id)
    pointer = read_json(scenario_dir / "evidence" / "accepted-run.json")
    selected = run_id or pointer.get("run_id")
    if pointer.get("status") != "accepted" or not isinstance(selected, str) or pointer.get("run_id") != selected:
        raise _failure("Harness accepted pointer does not identify the requested run")
    destination = scenario_dir / "evidence" / "runs" / selected
    manifest = read_json(destination / "run-manifest.json")
    budget_usd, observable_calls = _usage_contract(scenario_dir)
    _validate_manifest_shape(manifest, scenario_id, selected, state="accepted", budget_usd=budget_usd, observable_calls=observable_calls)
    assertions = load_assertion_contract(root, scenario_id)["frozen"]
    scenario = load_scenario(root, scenario_id)
    _validate_position_variants(destination, scenario_dir, scenario, assertions, manifest)
    _validate_checksums(destination, require_review=True)
    _validate_safety(destination, root)
    screenshot_manifest = read_json(destination / "screenshots" / "screenshot-manifest.json")
    captures = screenshot_manifest.get("screenshots")
    if screenshot_manifest.get("scenario_id") != scenario_id or screenshot_manifest.get("run_id") != selected or not isinstance(captures, list) or len(captures) < 3:
        raise _failure("Harness accepted run does not contain the required screenshots")
    for capture in captures:
        path = _require_relative_file(destination, capture.get("file"), "accepted screenshot")
        if sha256_file(path) != capture.get("sha256") or list(png_dimensions(path)) != [capture.get("width"), capture.get("height")]:
            raise _failure("Harness accepted screenshot identity is invalid")
    return {"status": "pass", "scenario_id": scenario_id, "run_id": selected, "proof_scope": "archive_integrity", "live_reexecution": False, "screenshots": len(captures), "external_calls": 0}
