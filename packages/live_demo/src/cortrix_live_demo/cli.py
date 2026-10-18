"""Thin command-line entry points for the live demo package."""

from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigurationError, load_config, validate_config


def status(config) -> dict:
    """Read runtime status without creating files or contacting dependencies."""
    workspace = config.runtime_root / "workspace.json"
    if not workspace.is_file():
        return {"status": "not_initialized", "scenario_id": config.scenario_id, "contract_version": config.contract_version}
    value = json.loads(workspace.read_text())
    return {
        "status": "initialized",
        "schema": value.get("schema"),
        "run_count": len(value.get("runs", [])),
        "request_count": len(value.get("requests", [])),
        "current_run_id": value.get("current_run_id"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cortrix-live-demo")
    parser.add_argument("--config", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-config")
    commands.add_parser("status")
    commands.add_parser("serve")
    provision_parser = commands.add_parser("provision")
    provision_parser.add_argument("--confirm-container-changes", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-config":
            print(json.dumps(validate_config(args.config), sort_keys=True))
            return 0
        config = load_config(args.config)
        if args.command == "status":
            print(json.dumps(status(config), sort_keys=True))
            return 0
        if args.command == "serve":
            from .server import serve
            serve(config)
            return 0
        if not args.confirm_container_changes:
            parser.error("provision requires --confirm-container-changes")
        from .provision import provision
        provision(config)
        return 0
    except ConfigurationError as exc:
        payload = {"error": {"code": "CORTRIX_LIVE_DEMO_CONFIG_INVALID", "message": str(exc)}}
    except (OSError, RuntimeError, ValueError):
        payload = {"error": {"code": "CORTRIX_LIVE_DEMO_COMMAND_FAILED", "message": "The live demo command failed; inspect private operator logs."}}
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
