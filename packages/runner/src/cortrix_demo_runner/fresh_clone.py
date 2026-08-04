from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .acceptance import verify_accepted
from .catalog import load_agent_manifest
from .errors import DemoContractError


REQUIRED_README_SECTIONS = ("## See the result", "## Run it locally", "## Inspect the evidence")


def verify_readme(text: str) -> None:
    positions = [text.find(section) for section in REQUIRED_README_SECTIONS]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise DemoContractError("README does not expose the three required first-run sections in order")
    if max(positions) > 5000:
        raise DemoContractError("README hides a required first-run section below its opening surface")


def verify_agent_bootstrap(clone: Path) -> dict[str, Any]:
    manifest = load_agent_manifest(clone)
    commands = manifest["bootstrap"]["safe_default"]
    required_commands = {
        "./democtl list --json",
        "./democtl describe --scenario order-api-field-migration --json",
        "./democtl validate --scenario order-api-field-migration",
        "./democtl verify-accepted",
    }
    if not required_commands.issubset(set(commands)):
        raise DemoContractError("Agent manifest does not expose the complete safe bootstrap")
    agent_instructions = (clone / "AGENTS.md").read_text(encoding="utf-8")
    if "## Agent Bootstrap" not in agent_instructions or any(command not in agent_instructions for command in required_commands):
        raise DemoContractError("AGENTS.md does not expose the complete safe bootstrap")
    return {"status": "pass", "entry": "agent.json", "commands": commands, "external_calls": 0}


def verify_fresh_clone(source: Path, run_id: str | None = None) -> dict[str, Any]:
    try:
        with tempfile.TemporaryDirectory(prefix="cortrix-demos-fresh-") as directory:
            clone = Path(directory) / "cortrix-demos"
            subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(source), str(clone)], check=True, capture_output=True, text=True)
            verify_readme((clone / "README.md").read_text(encoding="utf-8"))
            agent_bootstrap = verify_agent_bootstrap(clone)
            result = subprocess.run(["make", "validate"], cwd=clone, check=True, capture_output=True, text=True)
            license_text = (clone / "LICENSE").read_text(encoding="utf-8")
            if "Apache License" not in license_text or "Version 2.0" not in license_text or not (clone / "NOTICE").is_file():
                raise DemoContractError("Fresh clone does not contain the Apache-2.0 license and NOTICE contract")
            workflows = clone / ".github" / "workflows"
            if workflows.exists() and any(path.suffix in {".yml", ".yaml"} for path in workflows.rglob("*")):
                raise DemoContractError("Fresh clone unexpectedly contains a GitHub Actions workflow")
            accepted = verify_accepted(clone, run_id) if run_id else None
            commit = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            return {"status": "pass", "commit": commit, "readme_sections": list(REQUIRED_README_SECTIONS), "agent_bootstrap": agent_bootstrap, "make_validate": "pass", "accepted_run": accepted, "validation_output_recorded": bool(result.stdout)}
    except subprocess.CalledProcessError as exc:
        raise DemoContractError(f"Fresh clone verification command failed with exit code {exc.returncode}") from exc


def render_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=True, indent=2)
