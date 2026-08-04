from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from .errors import DemoContractError
from .io import read_json
from .scenario import RELEASE_COMMIT, SOURCE_REVISION


REVIEWED_ATTEMPT_LIMITS = (2, 3, 4, 5)


def require_api_key() -> None:
    value = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if len(value) < 20:
        raise DemoContractError("DEEPSEEK_API_KEY is missing; no external call was made")


def verify_source(source: Path) -> dict[str, str]:
    if not (source / ".git").exists():
        raise DemoContractError("Pinned Cortrix source checkout is missing")
    head = _git(source, "rev-parse", "HEAD")
    if head != SOURCE_REVISION:
        raise DemoContractError(f"Cortrix source revision mismatch: {head}")
    ancestor = subprocess.run(
        ["git", "-C", str(source), "merge-base", "--is-ancestor", RELEASE_COMMIT, SOURCE_REVISION],
        capture_output=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise DemoContractError("The validated source revision does not descend from the release commit")
    return {"release_commit": RELEASE_COMMIT, "source_revision": head}


def verify_pricing_snapshot(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if value.get("official_url") != "https://api-docs.deepseek.com/quick_start/pricing":
        raise DemoContractError("Pricing snapshot does not use the official DeepSeek pricing URL")
    if value.get("model") != "deepseek-v4-flash":
        raise DemoContractError("Pricing snapshot model does not match deepseek-v4-flash")
    if value.get("currency") != "USD":
        raise DemoContractError("Pricing snapshot currency must be USD")
    if not value.get("observed_at") or not isinstance(value.get("prices_per_million_tokens"), dict):
        raise DemoContractError("Pricing snapshot is incomplete")
    return value


def verify_runtime() -> dict[str, str]:
    docker = subprocess.run(["docker", "version", "--format", "{{.Client.Version}} {{.Server.Version}}"], capture_output=True, text=True, check=False)
    if docker.returncode != 0:
        raise DemoContractError("Docker runtime is unavailable")
    compose = subprocess.run(["docker-compose", "version", "--short"], capture_output=True, text=True, check=False)
    if compose.returncode != 0:
        raise DemoContractError("Docker Compose is unavailable")
    return {"docker": docker.stdout.strip(), "docker_compose": compose.stdout.strip()}


def full_stack_preflight(source: Path, pricing_snapshot: Path, reviewed_attempt_limit: int = 2, budget_usd: float = 1.0) -> dict[str, Any]:
    if reviewed_attempt_limit not in REVIEWED_ATTEMPT_LIMITS:
        raise DemoContractError("The reviewed Full Stack attempt limit must be 2, 3, 4, or 5")
    require_api_key()
    return {
        "secret_present": True,
        "secret_value_recorded": False,
        "source": verify_source(source),
        "runtime": verify_runtime(),
        "pricing": verify_pricing_snapshot(pricing_snapshot),
        "budget_usd": budget_usd,
        "max_full_stack_attempts": reviewed_attempt_limit,
        "local_generative_llm": False,
    }


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()
