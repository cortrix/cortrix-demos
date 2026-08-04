from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from .acceptance import record_screenshot, stage_accepted, verify_accepted
from .catalog import describe_scenario, list_scenarios, load_external_call_policy, require_runnable_scenario, validate_catalog
from .errors import DemoContractError
from .fresh_clone import verify_fresh_clone
from .io import read_json, write_json
from .live import execute_with_retry
from .preflight import REVIEWED_ATTEMPT_LIMITS, full_stack_preflight
from .resolver import apply_lifecycle_resolver
from .safety import require_safe
from .scenario import SCENARIO_ID, load_assertion_contract, scenario_root, validate_scenario


def command_validate(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    failures = validate_scenario(root, args.scenario)
    failures.extend(validate_catalog(root))
    require_safe(root)
    if failures:
        raise DemoContractError("Scenario validation failed:\n- " + "\n- ".join(failures))
    print(json.dumps({"status": "pass", "scenario": args.scenario, "external_calls": 0}, indent=2))


def command_list(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    scenarios = list_scenarios(root)
    print(json.dumps({"schema_version": 1, "scenarios": scenarios, "external_calls": 0}, ensure_ascii=True, indent=2))


def command_describe(args: argparse.Namespace) -> None:
    print(json.dumps(describe_scenario(args.root.resolve(), args.scenario), ensure_ascii=True, indent=2))


def command_public_safety(args: argparse.Namespace) -> None:
    require_safe(args.root.resolve())
    print(json.dumps({"status": "pass", "external_calls": 0}, indent=2))


def command_preflight(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    require_runnable_scenario(root, args.scenario, args.profile)
    if args.profile != "full-stack":
        raise DemoContractError("Only the full-stack live profile has a runtime preflight")
    policy = load_external_call_policy(root)
    result = full_stack_preflight(args.cortrix_source.resolve(), args.pricing_snapshot.resolve(), budget_usd=float(policy["budget_usd"]))
    print(json.dumps(result, ensure_ascii=True, indent=2))


def command_resolve(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    fixtures = read_json(scenario_root(root, args.scenario) / "fixtures" / "manifest.json")
    frozen_assertions = load_assertion_contract(root, args.scenario)["frozen"]
    result = apply_lifecycle_resolver(read_json(args.response), fixtures, read_json(args.identity_map), frozen_assertions)
    if not result["pass"]:
        raise DemoContractError("Application lifecycle resolver assertions failed")
    write_json(args.output, result)
    print(json.dumps({"status": "pass", "output": str(args.output)}, indent=2))


def command_run_full_stack(args: argparse.Namespace) -> None:
    require_runnable_scenario(args.root.resolve(), args.scenario, "full-stack")
    result = execute_with_retry(args.root.resolve(), args.cortrix_source.resolve(), args.pricing_snapshot.resolve(), args.reviewed_attempt_limit)
    print(json.dumps({"status": result["state"], "run_id": result["run_id"], "external_calls": True, "human_review_required": True}, indent=2))


def command_stage_accepted(args: argparse.Namespace) -> None:
    result = stage_accepted(args.root.resolve(), args.run_id, args.clean_room_review_id)
    print(json.dumps(result, ensure_ascii=True, indent=2))


def command_record_screenshot(args: argparse.Namespace) -> None:
    result = record_screenshot(args.root.resolve(), args.run_id, args.file.resolve(), args.route, args.evidence_path)
    print(json.dumps(result, ensure_ascii=True, indent=2))


def command_verify_accepted(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    run_id = args.run_id or describe_scenario(root, args.scenario)["accepted_evidence"]["run_id"]
    if not isinstance(run_id, str) or not run_id:
        raise DemoContractError("Accepted evidence pointer does not identify a run")
    print(json.dumps(verify_accepted(root, run_id), ensure_ascii=True, indent=2))


def command_fresh_clone_verify(args: argparse.Namespace) -> None:
    print(json.dumps(verify_fresh_clone(args.root.resolve(), args.run_id), ensure_ascii=True, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run and validate evidence-backed Cortrix demos.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    listing = subparsers.add_parser("list")
    listing.add_argument("--root", type=Path, default=Path.cwd())
    listing.add_argument("--json", action="store_true", help="Compatibility flag; output is always JSON.")
    listing.set_defaults(handler=command_list)

    describe = subparsers.add_parser("describe")
    describe.add_argument("--root", type=Path, default=Path.cwd())
    describe.add_argument("--scenario", required=True)
    describe.add_argument("--json", action="store_true", help="Compatibility flag; output is always JSON.")
    describe.set_defaults(handler=command_describe)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--root", type=Path, default=Path.cwd())
    validate.add_argument("--scenario", default=SCENARIO_ID)
    validate.set_defaults(handler=command_validate)

    safety = subparsers.add_parser("public-safety")
    safety.add_argument("--root", type=Path, default=Path.cwd())
    safety.set_defaults(handler=command_public_safety)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--root", type=Path, default=Path.cwd())
    preflight.add_argument("--scenario", default=SCENARIO_ID)
    preflight.add_argument("--profile", default="full-stack")
    preflight.add_argument("--cortrix-source", type=Path, default=Path(".runtime/cortrix-src"))
    preflight.add_argument("--pricing-snapshot", type=Path, default=Path(".runs/pricing-snapshot.json"))
    preflight.set_defaults(handler=command_preflight)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--root", type=Path, default=Path.cwd())
    resolve.add_argument("--scenario", default=SCENARIO_ID)
    resolve.add_argument("--response", type=Path, required=True)
    resolve.add_argument("--identity-map", type=Path, required=True)
    resolve.add_argument("--output", type=Path, required=True)
    resolve.set_defaults(handler=command_resolve)

    live = subparsers.add_parser("run-full-stack")
    live.add_argument("--root", type=Path, default=Path.cwd())
    live.add_argument("--scenario", default=SCENARIO_ID)
    live.add_argument("--cortrix-source", type=Path, default=Path(".runtime/cortrix-src"))
    live.add_argument("--pricing-snapshot", type=Path, default=Path(".runs/pricing-snapshot.json"))
    live.add_argument("--reviewed-attempt-limit", type=int, choices=REVIEWED_ATTEMPT_LIMITS, default=2, help="Use 3, 4, or 5 only when an explicit Human Review authorizes that exact cumulative limit.")
    live.set_defaults(handler=command_run_full_stack)

    accepted = subparsers.add_parser("stage-accepted")
    accepted.add_argument("--root", type=Path, default=Path.cwd())
    accepted.add_argument("--run-id", required=True)
    accepted.add_argument("--clean-room-review-id", required=True)
    accepted.set_defaults(handler=command_stage_accepted)

    screenshot = subparsers.add_parser("record-screenshot")
    screenshot.add_argument("--root", type=Path, default=Path.cwd())
    screenshot.add_argument("--run-id", required=True)
    screenshot.add_argument("--file", type=Path, required=True)
    screenshot.add_argument("--route", default="/packages/viewer/index.html")
    screenshot.add_argument("--evidence-path", default="run-manifest.json")
    screenshot.set_defaults(handler=command_record_screenshot)

    verify = subparsers.add_parser("verify-accepted")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    verify.add_argument("--scenario", default=SCENARIO_ID)
    verify.add_argument("--run-id", help="Accepted run ID. Omit it to follow the scenario's accepted-run pointer.")
    verify.set_defaults(handler=command_verify_accepted)

    fresh = subparsers.add_parser("fresh-clone-verify")
    fresh.add_argument("--root", type=Path, default=Path.cwd())
    fresh.add_argument("--run-id")
    fresh.set_defaults(handler=command_fresh_clone_verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except (DemoContractError, OSError, subprocess.CalledProcessError) as exc:
        message = str(exc)
        paths = [Path.cwd().resolve()]
        paths.extend(value.resolve() for value in vars(args).values() if isinstance(value, Path))
        for path in sorted({str(path) for path in paths}, key=len, reverse=True):
            message = message.replace(path, "[local-path]")
        if isinstance(exc, DemoContractError):
            payload = exc.as_dict(message)
        else:
            payload = {
                "error": {
                    "code": "CX_DEMO_RUNTIME_ERROR",
                    "category": "runtime",
                    "retryable": False,
                    "message": message,
                    "structured_data": {},
                }
            }
        print(json.dumps(payload, ensure_ascii=True), file=sys.stderr)
        return 1
    return 0
