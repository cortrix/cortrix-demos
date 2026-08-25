#!/usr/bin/env python3
"""Execute one frozen, budget-bounded Harness comparison campaign."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from typing import Any
from urllib.request import urlopen


SCENARIOS = ("database-change-conflict-guardian", "api-version-drift-coding-agent")
HARNESS_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
CORTRIX_COMMIT = "4c0f0f96b652d5662a66d047771826a4d2933739"
PLUGIN_COMMIT = "5b43a744c2fa93ddb95715b7783943757eb64b4e"
MODEL_MANIFEST_SHA256 = "b5c36a2b95d6c9cf9742eda121ac2cd68904df7acddc2de0cd88965a8b8401ce"
IMAGE = "cortrix:quickstart"
COMPOSE_PROJECT = "cortrix_demos_harness_foundation"
CAMPAIGN_ID = "deepseek-harness-cortrix-foundation"
SOURCE_PROJECTION_SCENARIO = SCENARIOS[0]
SCENARIO_CONTRACTS: dict[str, dict[str, Any]] = {scenario: {"id": scenario, "position_variants": []} for scenario in SCENARIOS}
CORTRIX_BASE_URL = "http://127.0.0.1:18430"
MAX_PROMPT_BYTES = 131_072
ANSWER_CALLS = 4
MAX_OUTPUT_TOKENS_PER_ANSWER = 2_048
BUDGET_USD = 1.0
HEADLESS_RUNTIME_EXPORTS = (
    "apps/cli/lib/bin.js",
    "packages/typert/registry/lib/index.js",
    "packages/api/gateway/lib/index.js",
)


class CampaignFailure(RuntimeError):
    """A stable campaign failure."""


def load_campaign_contract(path: Path) -> dict[str, Any]:
    contract = read_json(path)
    scenarios = contract.get("scenarios")
    ids = [item.get("id") for item in scenarios if isinstance(item, dict)] if isinstance(scenarios, list) else []
    if contract.get("schema_version") != 1 or not ids or len(ids) != len(set(ids)):
        raise CampaignFailure("campaign contract scenario identity is invalid")
    if not isinstance(contract.get("campaign_id"), str) or not isinstance(contract.get("compose_project"), str):
        raise CampaignFailure("campaign contract identity is missing")
    if not isinstance(contract.get("answer_calls"), int) or contract["answer_calls"] < 2:
        raise CampaignFailure("campaign answer call contract is invalid")
    if not isinstance(contract.get("budget_usd"), (int, float)) or not 0 < contract["budget_usd"] <= 5:
        raise CampaignFailure("campaign budget must be within USD 5.00")
    if contract.get("source_projection_scenario") not in ids:
        raise CampaignFailure("campaign source projection scenario is invalid")
    expected_answers = 0
    for item in scenarios:
        variants = item.get("position_variants", [])
        if not isinstance(variants, list) or any(value not in {"front", "middle", "end"} for value in variants):
            raise CampaignFailure("campaign position variants are invalid")
        if variants and (variants != ["front", "middle", "end"] or item.get("primary_variant") not in variants):
            raise CampaignFailure("campaign variant aggregate contract is invalid")
        expected_answers += 2 * max(1, len(variants))
    if expected_answers != contract["answer_calls"]:
        raise CampaignFailure("campaign answer call count does not match its scenario graph")
    return contract


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CampaignFailure(f"expected a JSON object in {path.name}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic text"
        raise CampaignFailure(f"command failed ({command[0]}): {diagnostic}")
    return completed


def git_identity(path: Path, expected: str, label: str) -> str:
    head = execute(["git", "-C", str(path), "rev-parse", "HEAD"], cwd=path).stdout.strip()
    if head != expected:
        raise CampaignFailure(f"{label} checkout does not match the frozen commit")
    status = execute(["git", "-C", str(path), "status", "--short", "--untracked-files=all"], cwd=path).stdout.strip()
    if status:
        raise CampaignFailure(f"{label} checkout is not clean")
    return head


def demo_identity(root: Path, expected_commit: str) -> str:
    branch = execute(["git", "-C", str(root), "branch", "--show-current"], cwd=root).stdout.strip()
    status = execute(["git", "-C", str(root), "status", "--short", "--untracked-files=all"], cwd=root).stdout.strip()
    if branch != "main" or status:
        raise CampaignFailure("demo checkout must be a clean main branch")
    head = execute(["git", "-C", str(root), "rev-parse", "HEAD"], cwd=root).stdout.strip()
    if head != expected_commit:
        raise CampaignFailure("demo checkout does not match the reviewed commit")
    return head


def image_identity(root: Path) -> str:
    label = "org.opencontainers.image.revision"
    output = execute(["docker", "image", "inspect", IMAGE, "--format", f"{{{{.Id}}}} {{{{index .Config.Labels \"{label}\"}}}}"], cwd=root).stdout.strip().split()
    if len(output) != 2 or output[1] != CORTRIX_COMMIT:
        raise CampaignFailure("Cortrix image revision does not match the frozen commit")
    return output[0]


def verify_volume_models(root: Path, volume: str) -> dict[str, Any]:
    manifest_path = root / "runtime" / "model-manifest.json"
    if sha256(manifest_path) != MODEL_MANIFEST_SHA256:
        raise CampaignFailure("model manifest does not match the reviewed contract")
    manifest = read_json(manifest_path)
    assets = manifest.get("assets")
    expected_components = {"embedding_model", "embedding_tokenizer", "reranker_model", "reranker_tokenizer"}
    if not isinstance(assets, list) or len(assets) != 4 or {asset.get("component") for asset in assets if isinstance(asset, dict)} != expected_components:
        raise CampaignFailure("model manifest does not contain the reviewed asset set")
    paths = [str(asset.get("container_path", "")) for asset in assets if isinstance(asset, dict)]
    if len(paths) != len(assets) or any(not path.startswith("/data/models/") for path in paths):
        raise CampaignFailure("model manifest contains an unsupported cache path")
    output = execute(
        ["docker", "run", "--rm", "--network", "none", "--entrypoint", "sha256sum", "-v", f"{volume}:/data:ro", IMAGE, *paths],
        cwd=root,
        timeout=600,
    ).stdout.splitlines()
    actual = {line.split()[1]: line.split()[0] for line in output if len(line.split()) == 2}
    projected = []
    for asset in assets:
        path = asset["container_path"]
        matches = actual.get(path) == asset.get("sha256")
        projected.append({"component": asset["component"], "model": asset["model"], "sha256": actual.get(path), "match": matches})
    if not all(item["match"] for item in projected):
        raise CampaignFailure("verified local model cache does not match the frozen checksums")
    return {"schema_version": 1, "all_match": True, "cache_action": "reused", "downloads": 0, "assets": projected}


def verify_volume_runtime_access(root: Path, volume: str) -> dict[str, Any]:
    """Verify that the image's default runtime user can write the data root."""
    try:
        execute(
            ["docker", "run", "--rm", "--network", "none", "--entrypoint", "sh", "-v", f"{volume}:/data", IMAGE, "-c", "test -w /data"],
            cwd=root,
            timeout=60,
        )
    except CampaignFailure as exc:
        raise CampaignFailure("Cortrix data volume is not writable by the runtime user") from exc
    return {"schema_version": 1, "runtime_user_can_write_data": True}


def verify_harness_headless_runtime(root: Path, harness_root: Path) -> dict[str, Any]:
    """Load the complete Headless profile without a provider credential or task."""
    for relative in HEADLESS_RUNTIME_EXPORTS:
        if not (harness_root / relative).is_file():
            raise CampaignFailure(f"DeepSeek Harness runtime export is missing: {relative}")

    with TemporaryDirectory(prefix="cortrix-demos-harness-headless-") as directory:
        home = Path(directory)
        environment = os.environ.copy()
        for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "CORTRIX_LLM_SECRET_FILE"):
            environment.pop(name, None)
        environment.update({
            "DSH_HOME": str(home),
            "DSH_PERMISSION_MODE": "read-only",
            "DSH_TELEMETRY_DISABLED": "1",
        })
        try:
            completed = execute(
                ["node", str(harness_root / HEADLESS_RUNTIME_EXPORTS[0]), "--profile", "headless", "--help"],
                cwd=root,
                environment=environment,
                timeout=120,
            )
        except CampaignFailure as exc:
            raise CampaignFailure("DeepSeek Harness Headless keyless load smoke failed") from exc
        if "Usage: dsh --profile headless" not in completed.stdout:
            raise CampaignFailure("DeepSeek Harness Headless keyless load smoke returned an unexpected interface")
        session_artifacts = list((home / "sessions").rglob("session.jsonl")) if (home / "sessions").exists() else []
        if session_artifacts:
            raise CampaignFailure("DeepSeek Harness Headless keyless load smoke created a session artifact")

    return {
        "schema_version": 1,
        "runtime_exports_present": True,
        "headless_help_loaded": True,
        "external_calls": 0,
        "session_artifacts": 0,
    }


def cli(root: Path, arguments: list[str]) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "packages" / "runner" / "src")
    execute([sys.executable, "-m", "cortrix_demo_runner", *arguments], cwd=root, environment=environment)


def require_compose(root: Path) -> tuple[list[str], str]:
    """Resolve a supported Compose CLI before any paid provider call."""
    candidates = ((["docker", "compose"], "docker compose"), (["docker-compose"], "docker-compose"))
    diagnostics: list[str] = []
    for command, label in candidates:
        try:
            completed = subprocess.run(
                [*command, "version"],
                cwd=root,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except OSError as exc:
            diagnostics.append(f"{label}: {exc.__class__.__name__}")
            continue
        if completed.returncode == 0:
            return command, label
        diagnostic = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        diagnostics.append(f"{label}: {diagnostic.splitlines()[0]}")
    raise CampaignFailure("Docker Compose is unavailable: " + "; ".join(diagnostics))


def compose(root: Path, compose_command: list[str], arguments: list[str], environment: dict[str, str]) -> None:
    execute([*compose_command, "-p", COMPOSE_PROJECT, "-f", str(root / "runtime" / "harness" / "docker-compose.yml"), *arguments], cwd=root, environment=environment, timeout=1800)


def exited_campaign_containers(root: Path) -> bool:
    output = execute(
        ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}", "--filter", "status=exited"],
        cwd=root,
    ).stdout.strip()
    return bool(output)


def wait_ready(root: Path, timeout_seconds: int = 1800) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(CORTRIX_BASE_URL + "/api/v1/system/health/ready", timeout=10) as response:
                value = json.loads(response.read().decode("utf-8"))
                if isinstance(value, dict):
                    return value
        except Exception:
            if exited_campaign_containers(root):
                raise CampaignFailure("Cortrix container exited before readiness")
            time.sleep(2)
    raise CampaignFailure("Cortrix readiness timed out")


def require_pricing(path: Path) -> tuple[dict[str, Any], float]:
    pricing = read_json(path)
    if pricing.get("official_url") != "https://api-docs.deepseek.com/quick_start/pricing" or pricing.get("model") != "deepseek-v4-flash":
        raise CampaignFailure("pricing snapshot identity is invalid")
    prices = pricing.get("prices_per_million_tokens")
    if not isinstance(prices, dict):
        raise CampaignFailure("pricing snapshot has no token price table")
    for key in ("input_cache_miss", "input_cache_hit", "output"):
        if not isinstance(prices.get(key), (int, float)) or prices[key] < 0:
            raise CampaignFailure("pricing snapshot contains an invalid price")
    input_bound = ANSWER_CALLS * MAX_PROMPT_BYTES + 64
    output_bound = ANSWER_CALLS * MAX_OUTPUT_TOKENS_PER_ANSWER + 8
    reviewed_bound = (input_bound * prices["input_cache_miss"] + output_bound * prices["output"]) / 1_000_000
    if reviewed_bound > BUDGET_USD:
        raise CampaignFailure("reviewed worst-case cost exceeds the campaign budget before external work")
    return pricing, reviewed_bound


def run_answer(root: Path, harness_root: Path, prompt: Path, answer_path: Path, usage_path: Path, home: Path) -> None:
    if len(prompt.read_bytes()) > MAX_PROMPT_BYTES:
        raise CampaignFailure("answer prompt exceeds the pre-reviewed byte bound")
    execute([
        sys.executable, str(root / "runtime" / "harness" / "run-answer.py"),
        "--root", str(root), "--harness-root", str(harness_root),
        "--prompt", str(prompt), "--answer", str(answer_path),
        "--usage", str(usage_path), "--home", str(home),
    ], cwd=root, timeout=900)


def resolve_answer(root: Path, scenario: str, mode: str, evidence: Path, answer: Path, output: Path) -> dict[str, Any]:
    cli(root, ["harness", "resolve", "--root", str(root), "--scenario", scenario, "--mode", mode, "--evidence", str(evidence), "--answer", str(answer), "--output", str(output)])
    return read_json(output)


def contract_smoke(root: Path, output: Path) -> dict[str, Any]:
    sys.path.insert(0, str(root / "packages" / "runner" / "src"))
    from cortrix_demo_runner.runtime import contract_smoke as call
    result = call()
    write_json(output, result)
    return result


def query_plugin(root: Path, plugin_root: Path, scenario: str, namespace: str, run_id: str, serial: int, output: Path, position_variant: str | None = None) -> None:
    session_id = f"{run_id}-{position_variant}-query-{serial}" if position_variant is not None else f"{run_id}-query-{serial}"
    command = [
        "node", str(root / "runtime" / "harness" / "query-plugin.mjs"),
        "--plugin-root", str(plugin_root),
        "--query-file", str(root / "scenarios" / scenario / "fixtures" / "query.txt"),
        "--namespace", namespace, "--base-url", CORTRIX_BASE_URL,
        "--max-results", "8", "--session-id", session_id,
        "--output", str(output),
    ]
    if position_variant is not None:
        command.extend(["--position-variant", position_variant])
    execute(command, cwd=root, timeout=300)


def fixture_operation(root: Path, scenario: str, namespace: str, output: Path, *, cleanup: bool = False, position_variant: str | None = None) -> None:
    command = [
        sys.executable, str(root / "runtime" / "harness" / "load-fixtures.py"),
        "--root", str(root), "--scenario", scenario,
        "--namespace", namespace, "--base-url", CORTRIX_BASE_URL,
        "--output", str(output),
    ]
    if cleanup:
        command.append("--cleanup")
    elif position_variant is not None:
        command.extend(["--position-variant", position_variant])
    execute(command, cwd=root, timeout=300 if cleanup else 1800)


def run_source_projection_probe(root: Path, plugin_root: Path, timestamp: str) -> dict[str, Any]:
    """Bind a real plugin result to frozen source identity before any paid LLM call."""
    scenario = SOURCE_PROJECTION_SCENARIO
    probe_id = f"source-projection-probe-{timestamp}"
    probe_root = root / ".runs" / probe_id
    namespace = "harness-probe-" + hashlib.sha256(probe_id.encode("utf-8")).hexdigest()[:24]
    ingestion = probe_root / "ingestion.json"
    tool_session = probe_root / "tool-session.json"
    evidence_path = probe_root / "evidence.json"
    cleanup_path = probe_root / "cleanup.json"
    receipt_path = probe_root / "receipt.json"
    probe_root.mkdir(parents=True, exist_ok=False)

    try:
        fixture_operation(root, scenario, namespace, ingestion)
        query_plugin(root, plugin_root, scenario, namespace, probe_id, 0, tool_session)
        cli(root, ["harness", "project-cortrix", "--root", str(root), "--scenario", scenario, "--tool-session", str(tool_session), "--output", str(evidence_path)])
        tool_result = read_json(tool_session)
        evidence = read_json(evidence_path)
        sources = source_sequence(evidence)
        tool_contract = evidence.get("tool_contract")
        if tool_result.get("external_llm_calls") != 0:
            raise CampaignFailure("source projection probe reported an external LLM call")
        if tool_result.get("registered_tools") != ["cortrix_search_evidence", "cortrix_get_source"]:
            raise CampaignFailure("source projection probe tool surface is invalid")
        if not sources or not isinstance(tool_contract, dict) or tool_contract.get("search_calls") != 1 or int(tool_contract.get("source_calls", 0)) < 1:
            raise CampaignFailure("source projection probe did not bind usable source evidence")
    finally:
        fixture_operation(root, scenario, namespace, cleanup_path, cleanup=True)

    cleanup = read_json(cleanup_path)
    if cleanup.get("removed_or_absent") is not True:
        raise CampaignFailure("source projection probe namespace cleanup failed")
    receipt = {
        "schema_version": 1,
        "probe": "cortrix_plugin_source_projection",
        "scenario_id": scenario,
        "registered_tools": ["cortrix_search_evidence", "cortrix_get_source"],
        "source_count": len(sources),
        "source_identity_bound": True,
        "external_llm_calls": 0,
        "namespace_removed_or_absent": True,
    }
    write_json(receipt_path, receipt)
    return receipt


def source_sequence(evidence: dict[str, Any]) -> list[tuple[str, str]]:
    items = evidence.get("evidence")
    if not isinstance(items, list):
        raise CampaignFailure("canonical Cortrix evidence is missing")
    return [(str(item.get("document_id")), str(item.get("source_sha256"))) for item in items if isinstance(item, dict)]


def run_comparison(
    root: Path,
    harness_root: Path,
    plugin_root: Path,
    scenario: str,
    run_id: str,
    comparison_root: Path,
    position_variant: str | None = None,
) -> list[Path]:
    run_a = comparison_root / "run-a"
    run_b = comparison_root / "run-b"
    home = comparison_root / "harness-home"
    comparison_root.mkdir(parents=True, exist_ok=False)
    variant_args = ["--position-variant", position_variant] if position_variant is not None else []

    baseline = run_a / "evidence.json"
    prompt_a = run_a / "answer-prompt.txt"
    answer_a = run_a / "answer.json"
    usage_a = run_a / "usage.json"
    resolver_a = run_a / "resolver.json"
    cli(root, ["harness", "baseline", "--root", str(root), "--scenario", scenario, "--output", str(baseline), *variant_args])
    cli(root, ["harness", "prompt", "--root", str(root), "--scenario", scenario, "--evidence", str(baseline), "--output", str(prompt_a)])
    run_answer(root, harness_root, prompt_a, answer_a, usage_a, home)
    result_a = resolve_answer(root, scenario, "cortrix_bundle_absent", baseline, answer_a, resolver_a)

    namespace_seed = f"{run_id}:{position_variant or 'default'}"
    namespace = "harness-" + hashlib.sha256(namespace_seed.encode("utf-8")).hexdigest()[:24]
    ingestion = run_b / "ingestion.json"
    cleanup = comparison_root / "cleanup.json"
    try:
        fixture_operation(root, scenario, namespace, ingestion, position_variant=position_variant)
        canonical = []
        for serial in (1, 2):
            tool_session = run_b / f"tool-session-{serial:02d}.json"
            evidence = run_b / f"evidence-{serial:02d}.json"
            query_plugin(root, plugin_root, scenario, namespace, run_id, serial, tool_session, position_variant)
            cli(root, ["harness", "project-cortrix", "--root", str(root), "--scenario", scenario, "--tool-session", str(tool_session), "--output", str(evidence), *variant_args])
            canonical.append(read_json(evidence))
        if source_sequence(canonical[0]) != source_sequence(canonical[1]):
            raise CampaignFailure("serial Cortrix query source order is not identical")
        prompt_b = run_b / "answer-prompt.txt"
        answer_b = run_b / "answer.json"
        usage_b = run_b / "usage.json"
        resolver_b = run_b / "resolver.json"
        cli(root, ["harness", "prompt", "--root", str(root), "--scenario", scenario, "--evidence", str(run_b / "evidence-01.json"), "--output", str(prompt_b)])
        run_answer(root, harness_root, prompt_b, answer_b, usage_b, home)
        result_b = resolve_answer(root, scenario, "cortrix_bundle_loaded", run_b / "evidence-01.json", answer_b, resolver_b)
    finally:
        fixture_operation(root, scenario, namespace, cleanup, cleanup=True)

    variant_field = {"position_variant": position_variant} if position_variant is not None else {}
    write_json(run_a / "summary.json", {"schema_version": 1, "run_id": run_id, "scenario_id": scenario, **variant_field, "backend_mode": "cortrix_bundle_absent", "pass": result_a["pass"], "authority_pass": result_a["authority_pass"], "expected_outcome_observed": result_a["expected_outcome_observed"], "evidence": "run-a/evidence.json", "answer": "run-a/answer.json", "usage": "run-a/usage.json", "resolver": "run-a/resolver.json"})
    write_json(run_b / "summary.json", {"schema_version": 1, "run_id": run_id, "scenario_id": scenario, **variant_field, "backend_mode": "cortrix_bundle_loaded", "pass": result_b["pass"], "authority_pass": result_b["authority_pass"], "expected_outcome_observed": result_b["expected_outcome_observed"], "serial_query_count": 2, "serial_source_order_identical": True, "tool_sessions": ["run-b/tool-session-01.json", "run-b/tool-session-02.json"], "evidence": "run-b/evidence-01.json", "answer": "run-b/answer.json", "usage": "run-b/usage.json", "resolver": "run-b/resolver.json"})
    return [usage_a, usage_b]


def run_scenario(root: Path, harness_root: Path, plugin_root: Path, scenario: str, timestamp: str) -> tuple[str, list[Path]]:
    run_id = f"{scenario}-{timestamp}"
    run_root = root / ".runs" / run_id
    paths = run_comparison(root, harness_root, plugin_root, scenario, run_id, run_root)
    return run_id, paths


def run_variant_scenario(root: Path, harness_root: Path, plugin_root: Path, scenario: str, timestamp: str, contract: dict[str, Any]) -> tuple[str, list[Path]]:
    run_id = f"{scenario}-{timestamp}"
    run_root = root / ".runs" / run_id
    variants_root = run_root / "position-variants"
    usages: list[Path] = []
    results = []
    for variant in contract["position_variants"]:
        comparison_root = variants_root / variant
        usages.extend(run_comparison(root, harness_root, plugin_root, scenario, run_id, comparison_root, variant))
        run_a = read_json(comparison_root / "run-a" / "summary.json")
        run_b = read_json(comparison_root / "run-b" / "summary.json")
        resolver = read_json(comparison_root / "run-b" / "resolver.json")
        cleanup = read_json(comparison_root / "cleanup.json")
        results.append({"variant": variant, "run_a_pass": run_a["pass"], "run_b_pass": run_b["pass"], "authority_pass": run_b["authority_pass"], "resolver_pass": resolver["pass"], "cleanup_pass": cleanup.get("removed_or_absent") is True})
    aggregate_pass = all(all(item[key] is True for key in ("run_a_pass", "run_b_pass", "authority_pass", "resolver_pass", "cleanup_pass")) for item in results)
    summary = {"schema_version": 1, "scenario_id": scenario, "run_id": run_id, "primary_variant": contract["primary_variant"], "variants": results, "all_variants_pass": aggregate_pass}
    write_json(variants_root / "summary.json", summary)
    if not aggregate_pass:
        raise CampaignFailure("position variant aggregate did not pass")
    primary = variants_root / contract["primary_variant"]
    shutil.copytree(primary / "run-a", run_root / "run-a")
    shutil.copytree(primary / "run-b", run_root / "run-b")
    write_json(run_root / "cleanup.json", {"schema_version": 1, "operation": "cleanup", "removed_or_absent": True, "position_variants": contract["position_variants"], "all_variant_namespaces_removed": True, "external_llm_calls": 0})
    return run_id, usages


def cleanup_campaign_containers(root: Path, compose_command: list[str] | None, environment: dict[str, str], *, attempted: bool) -> dict[str, Any]:
    """Stop the disposable campaign runtime and preserve an explicit outcome."""
    if compose_command is None or not attempted:
        return {"attempted": False, "compose_down_pass": None, "containers_absent": None, "error": None}

    errors: list[str] = []
    compose_down_pass = False
    containers_absent = False
    try:
        compose(root, compose_command, ["down", "--remove-orphans"], environment)
        compose_down_pass = True
    except Exception as exc:
        errors.append(f"compose down: {exc}")
    try:
        remaining = execute(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}"],
            cwd=root,
        ).stdout.strip()
        containers_absent = not bool(remaining)
        if remaining:
            errors.append("campaign containers remain")
    except Exception as exc:
        errors.append(f"container inspection: {exc}")
    return {
        "attempted": True,
        "compose_down_pass": compose_down_pass,
        "containers_absent": containers_absent,
        "error": "; ".join(errors) or None,
    }


def finish_cleanup(root: Path, compose_command: list[str], run_ids: list[str], environment: dict[str, str], volume: str) -> None:
    container_cleanup = cleanup_campaign_containers(root, compose_command, environment, attempted=True)
    if container_cleanup["compose_down_pass"] is not True or container_cleanup["containers_absent"] is not True:
        raise CampaignFailure("Harness campaign container cleanup failed")
    for run_id in run_ids:
        path = root / ".runs" / run_id / "cleanup.json"
        receipt = read_json(path)
        receipt.update(
            {
                "compose_project": COMPOSE_PROJECT,
                "containers_absent": True,
                "runtime_secret_materialized": False,
                "model_cache_preserved": True,
                "model_volume_name_recorded": False,
            }
        )
        write_json(path, receipt)


def namespace_cleanup_targets(root: Path, timestamp: str) -> list[tuple[str, str, Path]]:
    """Return only namespaces whose run directories show that setup began."""
    targets: list[tuple[str, str, Path]] = []
    probe_id = f"source-projection-probe-{timestamp}"
    probe_root = root / ".runs" / probe_id
    if probe_root.exists():
        namespace = "harness-probe-" + hashlib.sha256(probe_id.encode("utf-8")).hexdigest()[:24]
        targets.append((SOURCE_PROJECTION_SCENARIO, namespace, probe_root / "cleanup.json"))
    for scenario in SCENARIOS:
        run_id = f"{scenario}-{timestamp}"
        run_root = root / ".runs" / run_id
        contract = SCENARIO_CONTRACTS[scenario]
        variants = contract.get("position_variants") or [None]
        for variant in variants:
            comparison_root = run_root / "position-variants" / variant if variant is not None else run_root
            if not comparison_root.exists():
                continue
            seed = f"{run_id}:{variant or 'default'}"
            namespace = "harness-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
            targets.append((scenario, namespace, comparison_root / "cleanup.json"))
    return targets


def finish_rejection_namespaces(root: Path, timestamp: str, *, runtime_ready: bool) -> dict[str, Any]:
    targets = namespace_cleanup_targets(root, timestamp)
    outcomes: list[dict[str, Any]] = []
    for scenario, namespace, receipt_path in targets:
        outcome: dict[str, Any] = {"scenario_id": scenario, "attempted": False, "removed_or_absent": None, "error": None}
        if receipt_path.is_file():
            try:
                existing = read_json(receipt_path)
                if existing.get("removed_or_absent") is True:
                    outcome["removed_or_absent"] = True
                    outcomes.append(outcome)
                    continue
            except (OSError, json.JSONDecodeError, CampaignFailure):
                pass
        if not runtime_ready:
            outcome["error"] = "runtime was not ready for namespace cleanup"
            outcomes.append(outcome)
            continue
        try:
            fixture_operation(root, scenario, namespace, receipt_path, cleanup=True)
            receipt = read_json(receipt_path)
            outcome["attempted"] = True
            outcome["removed_or_absent"] = receipt.get("removed_or_absent") is True
            if outcome["removed_or_absent"] is not True:
                outcome["error"] = "cleanup receipt did not confirm removal or absence"
        except Exception as exc:
            outcome["attempted"] = True
            outcome["error"] = str(exc)
        outcomes.append(outcome)
    all_removed = all(item["removed_or_absent"] is True for item in outcomes) if outcomes else True
    return {"targets_observed": len(outcomes), "all_removed_or_absent": all_removed, "outcomes": outcomes}


def observable_usage(root: Path, timestamp: str, smoke_path: Path, *, provider_call_may_have_occurred: bool) -> dict[str, Any]:
    calls = 0
    input_tokens = 0
    output_tokens = 0
    cache_hit_tokens = 0
    unreadable_usage_files = 0
    if smoke_path.is_file():
        try:
            smoke = read_json(smoke_path)
            calls += int(smoke.get("call_count", 1) or 1)
            usage = smoke.get("usage") if isinstance(smoke.get("usage"), dict) else {}
            input_tokens += int(usage.get("prompt_tokens", 0) or 0)
            output_tokens += int(usage.get("completion_tokens", 0) or 0)
            cache_hit_tokens += int(usage.get("prompt_cache_hit_tokens", 0) or 0)
        except (OSError, ValueError, json.JSONDecodeError, CampaignFailure):
            unreadable_usage_files += 1
    runs_root = root / ".runs"
    if runs_root.exists():
        for run_root in sorted(runs_root.glob(f"*-{timestamp}")):
            if not run_root.is_dir():
                continue
            for path in sorted(run_root.rglob("usage.json")):
                if "harness-home" in path.parts:
                    continue
                try:
                    value = read_json(path)
                    calls += int(value.get("call_count", 0) or 0)
                    input_tokens += int(value.get("input_tokens", 0) or 0)
                    output_tokens += int(value.get("output_tokens", 0) or 0)
                    cache_hit_tokens += int(value.get("cache_hit_tokens", 0) or 0)
                except (OSError, ValueError, json.JSONDecodeError, CampaignFailure):
                    unreadable_usage_files += 1
    visibility = "partial" if calls else ("unknown" if provider_call_may_have_occurred else "not_applicable")
    return {
        "visibility": visibility,
        "provider_call_may_have_occurred": provider_call_may_have_occurred,
        "observable_calls": calls,
        "observable_input_tokens": input_tokens,
        "observable_output_tokens": output_tokens,
        "observable_cache_hit_tokens": cache_hit_tokens,
        "unreadable_usage_files": unreadable_usage_files,
    }


def sanitize_error(message: str, paths: list[Path]) -> str:
    sanitized = message
    for path in sorted({str(item) for item in [*paths, Path.home()] if str(item)}, key=len, reverse=True):
        sanitized = sanitized.replace(path, "<local-path>")
    return re.sub(r"(?<![A-Za-z0-9])/(?:[^\s\"']+)", "<local-path>", sanitized)


def sanitize_structure(value: Any, paths: list[Path]) -> Any:
    if isinstance(value, str):
        return sanitize_error(value, paths)
    if isinstance(value, list):
        return [sanitize_structure(item, paths) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_structure(item, paths) for key, item in value.items()}
    return value


def write_rejection_receipt(
    root: Path,
    path: Path,
    *,
    timestamp: str,
    expected_demo_commit: str,
    error: Exception,
    usage: dict[str, Any],
    namespace_cleanup: dict[str, Any],
    container_cleanup: dict[str, Any],
    identity_paths: list[Path],
) -> None:
    cleanup_pass = namespace_cleanup["all_removed_or_absent"] is True and container_cleanup["containers_absent"] in {True, None}
    safe_namespace_cleanup = sanitize_structure(namespace_cleanup, identity_paths)
    safe_container_cleanup = sanitize_structure(container_cleanup, identity_paths)
    write_json(path, {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "state": "rejected",
        "timestamp": timestamp,
        "expected_demo_commit": expected_demo_commit if len(expected_demo_commit) == 40 and all(character in "0123456789abcdef" for character in expected_demo_commit) else "invalid",
        "error": {
            "code": "CX_DEMO_HARNESS_CAMPAIGN_FAILED",
            "category": "permanent",
            "retryable": False,
            "message": sanitize_error(str(error), identity_paths),
        },
        "provider": {"provider": "deepseek", "model": "deepseek-v4-flash", "local_generative_llm": False},
        "usage": usage,
        "cleanup": {"namespaces": safe_namespace_cleanup, "containers": safe_container_cleanup, "pass": cleanup_pass},
        "promotion_allowed": False,
        "screenshot_eligible": False,
        "human_review_required": True,
    })


def usage_projection(pricing: dict[str, Any], usage_paths: list[Path], smoke: dict[str, Any], reviewed_bound: float) -> dict[str, Any]:
    calls = 1
    input_tokens = int(smoke.get("usage", {}).get("prompt_tokens", 0) or 0)
    output_tokens = int(smoke.get("usage", {}).get("completion_tokens", 0) or 0)
    cache_tokens = int(smoke.get("usage", {}).get("prompt_cache_hit_tokens", 0) or 0)
    for path in usage_paths:
        value = read_json(path)
        calls += int(value["call_count"])
        input_tokens += int(value["input_tokens"])
        output_tokens += int(value["output_tokens"])
        cache_tokens += int(value.get("cache_hit_tokens", 0))
    if calls != ANSWER_CALLS + 1:
        raise CampaignFailure("observable provider call count does not match the campaign answers plus one smoke")
    prices = pricing["prices_per_million_tokens"]
    miss_tokens = max(0, input_tokens - cache_tokens)
    cost = (miss_tokens * prices["input_cache_miss"] + cache_tokens * prices["input_cache_hit"] + output_tokens * prices["output"]) / 1_000_000
    if cost > BUDGET_USD:
        raise CampaignFailure("observable campaign cost exceeds the frozen budget")
    return {"visibility": "partial", "observable_calls": calls, "observable_input_tokens": input_tokens, "observable_output_tokens": output_tokens, "observable_cache_hit_tokens": cache_tokens, "observable_cost_usd": round(cost, 10), "reviewed_bound_usd": round(reviewed_bound, 10), "budget_usd": BUDGET_USD}


def build_manifest(root: Path, run_id: str, identities: dict[str, str], pricing: dict[str, Any], usage: dict[str, Any]) -> None:
    scenario = next(item for item in SCENARIOS if run_id.startswith(item + "-"))
    run_root = root / ".runs" / run_id
    usage_a = read_json(run_root / "run-a" / "usage.json")
    source_class = {"environment": "declared_environment", "explicit_profile": "secret_file", "default_profile": "default_profile"}.get(usage_a["secret_source"])
    if source_class is None:
        raise CampaignFailure("secret source class is invalid")
    cleanup = read_json(run_root / "cleanup.json")
    cleanup_pass = cleanup.get("removed_or_absent") is True and cleanup.get("containers_absent") is True and cleanup.get("runtime_secret_materialized") is False
    manifest = {
        "schema_version": 1,
        "scenario_id": scenario,
        "run_id": run_id,
        "state": "candidate",
        "source_identity": {
            **identities,
            "fixture_manifest_sha256": sha256(root / "scenarios" / scenario / "fixtures" / "manifest.json"),
            "assertion_contract_sha256": sha256(root / "scenarios" / scenario / "expected" / "assertions.json"),
            "answer_prompt_template_sha256": hashlib.sha256(b"deepseek-harness-cortrix-answer/v2").hexdigest(),
        },
        "comparison": {"same_harness": True, "same_model": True, "same_prompt": True, "same_corpus": True, "same_non_cortrix_tools": True, "only_independent_variable": "cortrix_bundle_loaded"},
        "provider": {"provider": "deepseek", "model": "deepseek-v4-flash", "local_generative_llm": False, "fallback_used": False, "secret_source": source_class, "secret_value_recorded": False},
        "usage": usage,
        "pricing_snapshot": pricing,
        "run_a": {"path": "run-a/summary.json", "sha256": sha256(run_root / "run-a" / "summary.json"), "pass": read_json(run_root / "run-a" / "summary.json")["pass"], "backend_mode": "cortrix_bundle_absent", "answer_prompt_sha256": sha256(run_root / "run-a" / "answer-prompt.txt")},
        "run_b": {"path": "run-b/summary.json", "sha256": sha256(run_root / "run-b" / "summary.json"), "pass": read_json(run_root / "run-b" / "summary.json")["pass"], "backend_mode": "cortrix_bundle_loaded", "answer_prompt_sha256": sha256(run_root / "run-b" / "answer-prompt.txt")},
        "resolver": {"path": "run-b/resolver.json", "sha256": sha256(run_root / "run-b" / "resolver.json"), "pass": read_json(run_root / "run-b" / "resolver.json")["pass"]},
        "cleanup": {"path": "cleanup.json", "sha256": sha256(run_root / "cleanup.json"), "pass": cleanup_pass},
        "screenshot_eligible": False,
        "human_review_required": True,
        "negative_result": False,
    }
    variants_summary = run_root / "position-variants" / "summary.json"
    if variants_summary.is_file():
        summary = read_json(variants_summary)
        manifest["position_variants"] = {"path": "position-variants/summary.json", "sha256": sha256(variants_summary), "pass": summary.get("all_variants_pass") is True}
    write_json(run_root / "run-manifest.json", manifest)
    files = []
    for path in sorted(run_root.rglob("*")):
        if path.is_file() and path.name != "checksums.json" and "harness-home" not in path.parts:
            files.append({"path": path.relative_to(run_root).as_posix(), "sha256": sha256(path)})
    write_json(run_root / "checksums.json", {"schema_version": 1, "run_id": run_id, "files": files})


def main() -> int:
    global SCENARIOS, SCENARIO_CONTRACTS, COMPOSE_PROJECT, CAMPAIGN_ID, SOURCE_PROJECTION_SCENARIO, ANSWER_CALLS, BUDGET_USD
    parser = argparse.ArgumentParser(description="Run one frozen Harness comparison campaign.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--harness-root", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--cortrix-root", type=Path, required=True)
    parser.add_argument("--pricing-snapshot", type=Path, required=True)
    parser.add_argument("--volume", default="cortrix_demos_harness_foundation_data")
    parser.add_argument("--campaign-contract", type=Path, default=Path("runtime/harness/campaigns/foundation.json"))
    parser.add_argument("--expected-demo-commit", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    harness_root = args.harness_root.resolve()
    plugin_root = args.plugin_root.resolve()
    cortrix_root = args.cortrix_root.resolve()
    pricing_path = args.pricing_snapshot.resolve()
    contract_path = (root / args.campaign_contract).resolve() if not args.campaign_contract.is_absolute() else args.campaign_contract.resolve()
    environment = os.environ.copy()
    environment["CORTRIX_HARNESS_VOLUME"] = args.volume
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    CAMPAIGN_ID = "deepseek-harness-cortrix-preflight"
    campaign_path = root / ".runs" / f"{CAMPAIGN_ID}-{timestamp}.json"
    rejection_path = root / ".runs" / f"{CAMPAIGN_ID}-{timestamp}-rejected.json"
    smoke_path = root / ".runs" / f"contract-smoke-{timestamp}.json"
    compose_attempted = False
    runtime_ready = False
    provider_call_may_have_occurred = False
    compose_command: list[str] | None = None
    compose_label: str | None = None
    try:
        if len(args.expected_demo_commit) != 40 or any(character not in "0123456789abcdef" for character in args.expected_demo_commit):
            raise CampaignFailure("expected Demos commit must be a full lowercase Git object ID")
        campaign_contract = load_campaign_contract(contract_path)
        SCENARIOS = tuple(item["id"] for item in campaign_contract["scenarios"])
        SCENARIO_CONTRACTS = {item["id"]: item for item in campaign_contract["scenarios"]}
        COMPOSE_PROJECT = campaign_contract["compose_project"]
        CAMPAIGN_ID = campaign_contract["campaign_id"]
        SOURCE_PROJECTION_SCENARIO = campaign_contract["source_projection_scenario"]
        ANSWER_CALLS = campaign_contract["answer_calls"]
        BUDGET_USD = float(campaign_contract["budget_usd"])
        campaign_path = root / ".runs" / f"{CAMPAIGN_ID}-{timestamp}.json"
        rejection_path = root / ".runs" / f"{CAMPAIGN_ID}-{timestamp}-rejected.json"
        pricing, reviewed_bound = require_pricing(pricing_path)
        identities = {
            "demo_commit": demo_identity(root, args.expected_demo_commit),
            "plugin_commit": git_identity(plugin_root, PLUGIN_COMMIT, "plugin"),
            "harness_commit": git_identity(harness_root, HARNESS_COMMIT, "Harness"),
            "cortrix_commit": git_identity(cortrix_root, CORTRIX_COMMIT, "Cortrix"),
            "cortrix_image_digest": image_identity(root),
        }
        model_checksums = verify_volume_models(root, args.volume)
        volume_access = verify_volume_runtime_access(root, args.volume)
        compose_command, compose_label = require_compose(root)
        headless_runtime = verify_harness_headless_runtime(root, harness_root)
        compose_attempted = True
        compose(root, compose_command, ["up", "-d"], environment)
        health = wait_ready(root)
        runtime_ready = True
        source_projection = run_source_projection_probe(root, plugin_root, timestamp)
        provider_call_may_have_occurred = True
        smoke_result = contract_smoke(root, smoke_path)
        usage_paths: list[Path] = []
        run_ids = []
        for scenario in SCENARIOS:
            scenario_contract = SCENARIO_CONTRACTS[scenario]
            if scenario_contract.get("position_variants"):
                run_id, paths = run_variant_scenario(root, harness_root, plugin_root, scenario, timestamp, scenario_contract)
            else:
                run_id, paths = run_scenario(root, harness_root, plugin_root, scenario, timestamp)
            run_ids.append(run_id)
            usage_paths.extend(paths)
            write_json(root / ".runs" / run_id / "runtime.json", {"schema_version": 1, "image": identities["cortrix_image_digest"], "source_revision": CORTRIX_COMMIT, "health": health, "compose_cli": compose_label, "model_checksums": model_checksums, "volume_access": volume_access, "harness_headless": headless_runtime, "source_projection_probe": source_projection, "model_cache_action": "reused", "downloads": 0, "builds": 0})
        usage = usage_projection(pricing, usage_paths, smoke_result, reviewed_bound)
        finish_cleanup(root, compose_command, run_ids, environment, args.volume)
        compose_attempted = False
        runtime_ready = False
        for run_id in run_ids:
            build_manifest(root, run_id, identities, pricing, usage)
        write_json(campaign_path, {"schema_version": 1, "campaign_id": CAMPAIGN_ID, "state": "candidate", "run_ids": run_ids, "source_projection_probe": source_projection, "shared_contract_smoke_calls": 1, "answer_calls": ANSWER_CALLS, "compose_cli": compose_label, "harness_headless": headless_runtime, "usage": usage, "downloads": 0, "builds": 0, "human_review_required": True})
        print(json.dumps({"status": "candidate", "run_ids": run_ids, "observable_calls": usage["observable_calls"], "observable_cost_usd": usage["observable_cost_usd"], "reviewed_bound_usd": usage["reviewed_bound_usd"], "budget_usd": BUDGET_USD}, ensure_ascii=True))
        return 0
    except Exception as exc:
        namespace_cleanup = finish_rejection_namespaces(root, timestamp, runtime_ready=runtime_ready)
        container_cleanup = cleanup_campaign_containers(root, compose_command, environment, attempted=compose_attempted)
        compose_attempted = False
        usage = observable_usage(root, timestamp, smoke_path, provider_call_may_have_occurred=provider_call_may_have_occurred)
        write_rejection_receipt(
            root,
            rejection_path,
            timestamp=timestamp,
            expected_demo_commit=args.expected_demo_commit,
            error=exc,
            usage=usage,
            namespace_cleanup=namespace_cleanup,
            container_cleanup=container_cleanup,
            identity_paths=[root, harness_root, plugin_root, cortrix_root, pricing_path, contract_path],
        )
        safe_message = sanitize_error(str(exc), [root, harness_root, plugin_root, cortrix_root, pricing_path, contract_path])
        print(json.dumps({"error": {"code": "CX_DEMO_HARNESS_CAMPAIGN_FAILED", "category": "permanent", "retryable": False, "message": safe_message, "rejection_receipt": rejection_path.name}}, ensure_ascii=True), file=sys.stderr)
        return 1
    finally:
        if compose_attempted:
            cleanup_campaign_containers(root, compose_command, environment, attempted=True)


if __name__ == "__main__":
    raise SystemExit(main())
