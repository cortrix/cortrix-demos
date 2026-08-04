"""Evidence-rich, guided execution for the educational demo surface.

The summaries returned here intentionally expose pipeline stages, ranking layers,
runtime identity, cleanup, and cost visibility so Agents and humans can audit the
comparison without reading implementation code. They are not a production
Cortrix API contract, and production clients do not need to expose this detail.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from .catalog import load_external_call_policy
from .errors import DemoContractError
from .io import read_json, write_json
from .live import failure_category, finalize_candidate, new_run_id, record_state, require_budget_bound, reserve_attempt, run_a, run_b, sanitized_error, update_attempt, validate_reviewed_attempt_limit, verify_demo_checkout
from .preflight import full_stack_preflight
from .runtime import cleanup, contract_smoke, ensure_image, start, verify_fixture_hashes, verify_models
from .scenario import SCENARIO_ID, load_assertion_contract, load_scenario, scenario_root, validate_scenario


CURRENT_POINTER = ".runs/walkthrough-current.json"
SESSION_FILE = "walkthrough-session.json"
PHASES = ("initialized", "run_a_complete", "run_b_complete", "candidate", "rejected")


def record_pricing_snapshot(
    root: Path,
    output: Path,
    input_cache_hit: float,
    input_cache_miss: float,
    output_price: float,
    observed_at: str | None = None,
) -> dict[str, Any]:
    prices = (input_cache_hit, input_cache_miss, output_price)
    if any(value < 0 for value in prices):
        raise DemoContractError("Pricing values must be non-negative")
    timestamp = observed_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot = {
        "schema_version": 1,
        "observed_at": timestamp,
        "official_url": "https://api-docs.deepseek.com/quick_start/pricing",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_version": "DeepSeek-V4-Flash",
        "currency": "USD",
        "unit": "per_million_tokens",
        "prices_per_million_tokens": {
            "input_cache_hit": input_cache_hit,
            "input_cache_miss": input_cache_miss,
            "output": output_price,
        },
        "notes": "Recorded from the official pricing page immediately before an authorized local walkthrough. A price change does not expand the repository budget.",
    }
    destination = output if output.is_absolute() else root / output
    write_json(destination, snapshot, mode=0o600)
    return {"status": "recorded", "path": destination.relative_to(root).as_posix(), **snapshot}


def session_path(root: Path, run_id: str) -> Path:
    return root / ".runs" / run_id / SESSION_FILE


def current_pointer_path(root: Path) -> Path:
    return root / CURRENT_POINTER


def resolve_run_id(root: Path, run_id: str | None) -> str:
    if run_id:
        return run_id
    pointer = current_pointer_path(root)
    if not pointer.is_file():
        raise DemoContractError("No current walkthrough exists; run walkthrough init first")
    value = read_json(pointer).get("run_id")
    if not isinstance(value, str) or not value:
        raise DemoContractError("The current walkthrough pointer is malformed")
    return value


def load_session(root: Path, run_id: str | None = None) -> dict[str, Any]:
    resolved = resolve_run_id(root, run_id)
    path = session_path(root, resolved)
    if not path.is_file():
        raise DemoContractError("The walkthrough session does not exist")
    session = read_json(path)
    if session.get("run_id") != resolved or session.get("phase") not in PHASES:
        raise DemoContractError("The walkthrough session identity or phase is invalid")
    return session


def save_session(root: Path, session: dict[str, Any]) -> None:
    write_json(session_path(root, session["run_id"]), session, mode=0o600)
    write_json(current_pointer_path(root), {"schema_version": 1, "run_id": session["run_id"]}, mode=0o600)


def require_phase(session: dict[str, Any], expected: str) -> None:
    if session.get("phase") != expected:
        raise DemoContractError(f"Walkthrough phase must be {expected}; current phase is {session.get('phase')}")


def verify_session_checkout(root: Path, session: dict[str, Any]) -> None:
    checkout = verify_demo_checkout(root)
    if checkout != session.get("demo_checkout"):
        raise DemoContractError("The demo checkout changed after walkthrough initialization")
    failures = validate_scenario(root)
    if failures:
        raise DemoContractError("Scenario validation failed: " + "; ".join(failures))


def reject_walkthrough(root: Path, session: dict[str, Any], phase: str, exc: Exception) -> None:
    run_id = session["run_id"]
    run_dir = root / ".runs" / run_id
    receipt = run_dir / "cleanup-receipt.json"
    if not receipt.exists():
        try:
            cleanup(run_id, receipt)
        except Exception:
            pass
    category = failure_category(exc)
    try:
        history = read_json(run_dir / "state-history.json")
        transitions = history.get("transitions") if isinstance(history, dict) else None
        if isinstance(transitions, list) and (not transitions or transitions[-1].get("state") not in {"candidate", "rejected"}):
            record_state(run_dir, "rejected", category)
    except Exception:
        pass
    update_attempt(root, run_id, "rejected", category, session["campaign_id"])
    write_json(
        run_dir / "rejection.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "state": "rejected",
            "phase": phase,
            "failure_category": category,
            "message": sanitized_error(exc),
            "screenshot_eligible": False,
        },
    )
    session["phase"] = "rejected"
    session["failed_phase"] = phase
    save_session(root, session)


def initialize_walkthrough(root: Path, source: Path, pricing_path: Path, reviewed_attempt_limit: int = 2) -> dict[str, Any]:
    failures = validate_scenario(root)
    if failures:
        raise DemoContractError("Scenario validation failed: " + "; ".join(failures))
    scenario = load_scenario(root)
    execution_contract = scenario["execution_contract"]
    campaign_id = execution_contract["campaign_id"]
    reviewed_attempt_limit = validate_reviewed_attempt_limit(reviewed_attempt_limit)
    if reviewed_attempt_limit > int(execution_contract["campaign_attempt_cap"]):
        raise DemoContractError("The reviewed attempt limit exceeds the sealed campaign cap")
    profile = read_json(scenario_root(root) / "profiles" / "full-stack.json")
    policy = load_external_call_policy(root)
    budget_usd = min(float(profile["budget_usd"]), float(policy["budget_usd"]))
    preflight = full_stack_preflight(source, pricing_path, reviewed_attempt_limit, budget_usd=budget_usd)
    pricing = read_json(pricing_path)
    bound = require_budget_bound({**profile, "budget_usd": budget_usd}, pricing, reviewed_attempt_limit)
    fixture_root = scenario_root(root) / "fixtures"
    fixture_manifest = read_json(fixture_root / "manifest.json")
    verify_fixture_hashes(fixture_root, fixture_manifest)
    demo_checkout = verify_demo_checkout(root)
    run_id = new_run_id()
    run_dir = root / ".runs" / run_id
    if run_dir.exists():
        raise DemoContractError("A walkthrough with the generated run ID already exists")
    attempt = reserve_attempt(root, run_id, reviewed_attempt_limit, campaign_id, scenario["scenario_version"], demo_checkout["commit"])
    record_state(run_dir, "created")
    record_state(run_dir, "running")
    session: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "scenario_id": SCENARIO_ID,
        "scenario_version": scenario["scenario_version"],
        "campaign_id": campaign_id,
        "campaign_slot": attempt,
        "reviewed_attempt_limit": reviewed_attempt_limit,
        "budget_usd": budget_usd,
        "maximum_reviewed_attempt_contract_cost_usd": bound,
        "demo_checkout": demo_checkout,
        "preflight": preflight,
        "pricing": pricing,
        "phase": "initialized",
    }
    try:
        session["image"] = ensure_image(source)
        save_session(root, session)
    except Exception as exc:
        reject_walkthrough(root, session, "image_identity", exc)
        raise
    return {
        "status": "initialized",
        "run_id": run_id,
        "phase": session["phase"],
        "scenario_version": scenario["scenario_version"],
        "campaign_slot": attempt,
        "demo_commit": demo_checkout["commit"],
        "budget_usd": budget_usd,
        "next_command": "./democtl walkthrough run-a",
    }


def execute_run_a_step(root: Path, run_id: str | None = None) -> dict[str, Any]:
    session = load_session(root, run_id)
    require_phase(session, "initialized")
    try:
        verify_session_checkout(root, session)
        start("embedding-only")
        models = verify_models()
        write_json(root / ".runs" / session["run_id"] / "model-checksums.json", models)
        scenario = load_scenario(root)
        fixture_root = scenario_root(root) / "fixtures"
        manifest = read_json(fixture_root / "manifest.json")
        frozen = load_assertion_contract(root)["frozen"]
        result = run_a(session["run_id"], root / ".runs" / session["run_id"], fixture_root, manifest, frozen, runtime_ready=True)
        session["phase"] = "run_a_complete"
        save_session(root, session)
        # Keep the educational boundary observable without exposing raw vectors
        # or local runtime paths. A production client would normally return only
        # the application result and its own required operational telemetry.
        return {
            "status": "pass",
            "run_id": session["run_id"],
            "phase": session["phase"],
            "runtime_profile": "embedding-only",
            "external_calls": 0,
            "postgresql_version": result["environment"]["postgresql_version"],
            "pgvector_version": result["environment"]["pgvector_version"],
            "inserted_block_count": result["inserted_block_count"],
            "top1": result["ranking"][0],
            "current_document_rank": next(item["rank"] for item in result["ranking"] if item["document_id"] == frozen["run_a_required_current_document_id"]),
            "assertions": result["assertions"],
            "next_command": "./democtl walkthrough inspect --component run-a",
        }
    except Exception as exc:
        reject_walkthrough(root, session, "run_a", exc)
        raise


def execute_run_b_step(root: Path, run_id: str | None = None) -> dict[str, Any]:
    session = load_session(root, run_id)
    require_phase(session, "run_a_complete")
    try:
        verify_session_checkout(root, session)
        health = start("full-stack")
        smoke = contract_smoke()
        run_dir = root / ".runs" / session["run_id"]
        write_json(run_dir / "contract-smoke.json", smoke)
        scenario = load_scenario(root)
        fixture_root = scenario_root(root) / "fixtures"
        manifest = read_json(fixture_root / "manifest.json")
        frozen = load_assertion_contract(root)["frozen"]
        result = run_b(session["run_id"], run_dir, fixture_root, manifest, frozen, scenario["retrieval_contract"])
        session["health"] = health
        session["phase"] = "run_b_complete"
        save_session(root, session)
        resolver = result["resolver"]
        # Show each ranking responsibility separately for the demo. These fields
        # are evidence projections, not fields that production applications must
        # copy into their user-facing responses.
        return {
            "status": "pass",
            "run_id": session["run_id"],
            "phase": session["phase"],
            "runtime_profile": "full-stack",
            "provider": smoke["provider"],
            "model": smoke["model"],
            "ingestion_completion": result["ingestion"]["completion"],
            "retrieval_paths": result["query_attempts"][0]["rrf_path_counts"],
            "bge_leader": resolver["layers"]["bge_cross_encoder"]["leader"],
            "final_top_result": resolver["layers"]["deepseek_listwise_final"]["top_result"],
            "resolver_decision": resolver["decision"],
            "repeat": result["repeat"],
            "cleanup_required": True,
            "next_command": "./democtl walkthrough inspect --component run-b",
        }
    except Exception as exc:
        reject_walkthrough(root, session, "run_b", exc)
        raise


def finalize_walkthrough(root: Path, run_id: str | None = None) -> dict[str, Any]:
    session = load_session(root, run_id)
    require_phase(session, "run_b_complete")
    try:
        verify_session_checkout(root, session)
        run_dir = root / ".runs" / session["run_id"]
        scenario = load_scenario(root)
        manifest = finalize_candidate(
            root,
            session["run_id"],
            scenario,
            session["campaign_slot"],
            session["image"],
            session["demo_checkout"],
            session["pricing"],
            session["maximum_reviewed_attempt_contract_cost_usd"],
            session["budget_usd"],
            session["preflight"],
            session["health"],
            read_json(run_dir / "contract-smoke.json"),
            read_json(run_dir / "model-checksums.json"),
            read_json(run_dir / "run-a" / "pgvector-result.json"),
            read_json(run_dir / "run-b" / "summary.json"),
        )
        session["phase"] = "candidate"
        save_session(root, session)
        return {
            "status": "candidate",
            "run_id": session["run_id"],
            "phase": session["phase"],
            "assertions": manifest["assertions"],
            "required_paths": manifest["required_paths"],
            "cleanup": manifest["cleanup"],
            "cost": manifest["cost"],
            "human_review_required": True,
            "next_command": "./democtl walkthrough inspect --component candidate",
        }
    except Exception as exc:
        reject_walkthrough(root, session, "candidate_finalize", exc)
        raise


def walkthrough_status(root: Path, run_id: str | None = None) -> dict[str, Any]:
    session = load_session(root, run_id)
    next_commands = {
        "initialized": "./democtl walkthrough run-a",
        "run_a_complete": "./democtl walkthrough run-b",
        "run_b_complete": "./democtl walkthrough finalize",
        "candidate": "./democtl walkthrough inspect --component candidate",
        "rejected": None,
    }
    return {
        "status": session["phase"],
        "run_id": session["run_id"],
        "scenario_version": session["scenario_version"],
        "campaign_slot": session["campaign_slot"],
        "demo_commit": session["demo_checkout"]["commit"],
        "next_command": next_commands[session["phase"]],
    }


def inspect_walkthrough(root: Path, component: str, run_id: str | None = None) -> dict[str, Any]:
    # Inspection is intentionally verbose and reads persisted evidence only. It
    # never recomputes a result or turns diagnostic detail into a production API.
    session = load_session(root, run_id)
    run_dir = root / ".runs" / session["run_id"]
    if component == "run-a":
        result = read_json(run_dir / "run-a" / "pgvector-result.json")
        return {
            "run_id": session["run_id"],
            "component": "run-a",
            "environment": result["environment"],
            "search": result["search"],
            "inserted_block_count": result["inserted_block_count"],
            "ranking": result["ranking"],
            "assertions": result["assertions"],
            "pass": result["pass"],
        }
    if component == "run-b":
        result = read_json(run_dir / "run-b" / "summary.json")
        resolver = read_json(run_dir / "run-b" / "resolver-01.json")
        return {
            "run_id": session["run_id"],
            "component": "run-b",
            "ingestion_completion": result["ingestion"]["completion"],
            "retrieval_paths": result["query_attempts"][0]["rrf_path_counts"],
            "query_checks": result["query_attempts"][0]["checks"],
            "layers": resolver["layers"],
            "decision": resolver["decision"],
            "repeat": result["repeat"],
            "pass": result["pass"] and resolver["pass"],
        }
    if component == "candidate":
        result = read_json(run_dir / "run-manifest.json")
        return {
            "run_id": session["run_id"],
            "component": "candidate",
            "state": result["state"],
            "target_identity": result["target_identity"],
            "required_paths": result["required_paths"],
            "assertions": result["assertions"],
            "cleanup": result["cleanup"],
            "cost": result["cost"],
            "human_review_required": result["human_review_required"],
        }
    raise DemoContractError("Walkthrough component must be run-a, run-b, or candidate")


def abort_walkthrough(root: Path, run_id: str | None = None) -> dict[str, Any]:
    session = load_session(root, run_id)
    if session["phase"] in {"candidate", "rejected"}:
        raise DemoContractError("Only an active walkthrough can be aborted")
    error = DemoContractError("Walkthrough aborted by the operator")
    reject_walkthrough(root, session, "operator_abort", error)
    receipt = read_json(root / ".runs" / session["run_id"] / "cleanup-receipt.json")
    return {"status": "rejected", "run_id": session["run_id"], "phase": "operator_abort", "cleanup": receipt}
