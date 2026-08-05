from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from .errors import DemoContractError
from .io import read_json


REVIEWED_ATTEMPT_LIMITS = (2, 3, 4, 5)


def require_api_key(secret_env: str = "DEEPSEEK_API_KEY") -> None:
    value = os.environ.get(secret_env, "").strip()
    if len(value) < 20:
        raise DemoContractError(
            f"{secret_env} is missing; no external call was made",
            code="CX_DEMO_SECRET_MISSING",
            category="auth",
            structured_data={
                "secret_env": secret_env,
                "external_calls_made": False,
                "next_action": f"Inject {secret_env} through the process environment, then rerun preflight.",
            },
        )


def verify_source(
    source: Path,
    *,
    release_commit: str,
    source_revision: str,
    source_repository: str | None = None,
    source_path: str = ".runtime/cortrix-src",
) -> dict[str, str]:
    if not (source / ".git").exists():
        raise DemoContractError(
            "Pinned Cortrix source checkout is missing",
            code="CX_DEMO_SOURCE_CHECKOUT_MISSING",
            structured_data={
                "required_path": source_path,
                "source_repository": source_repository,
                "source_revision": source_revision,
                "next_action": "Obtain the repository, check out the required revision, and rerun this command.",
            },
        )
    head = _git(source, "rev-parse", "HEAD")
    if head != source_revision:
        raise DemoContractError(
            "Cortrix source revision does not match the scenario contract",
            code="CX_DEMO_SOURCE_REVISION_MISMATCH",
            structured_data={
                "required_path": source_path,
                "expected_revision": source_revision,
                "actual_revision": head,
                "next_action": f"Check out {source_revision} in the pinned source directory.",
            },
        )
    ancestor = subprocess.run(
        ["git", "-C", str(source), "merge-base", "--is-ancestor", release_commit, source_revision],
        capture_output=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise DemoContractError(
            "The validated source revision does not descend from the release commit",
            code="CX_DEMO_SOURCE_ANCESTRY_INVALID",
            structured_data={"release_commit": release_commit, "source_revision": source_revision, "next_action": "Use the source history required by the scenario contract."},
        )
    return {"release_commit": release_commit, "source_revision": head}


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


def verify_runtime(retry_command: str = "preflight") -> dict[str, str]:
    try:
        docker = subprocess.run(["docker", "version", "--format", "{{.Client.Version}} {{.Server.Version}}"], capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise DemoContractError(
            "Docker CLI is unavailable",
            code="CX_DEMO_DOCKER_CLI_MISSING",
            structured_data={"requirement": "docker", "next_action": "Install Docker and make the docker command available on PATH."},
        ) from exc
    if docker.returncode != 0:
        raise DemoContractError(
            "Docker engine is unavailable",
            code="CX_DEMO_DOCKER_ENGINE_UNAVAILABLE",
            category="transient",
            retryable=True,
            retry_after_ms=1000,
            structured_data={"requirement": "docker_engine", "next_action": f"Start the Docker engine, wait until it is ready, and rerun {retry_command}."},
        )
    try:
        compose = subprocess.run(["docker-compose", "version", "--short"], capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise DemoContractError(
            "Docker Compose CLI is unavailable",
            code="CX_DEMO_COMPOSE_CLI_MISSING",
            structured_data={"requirement": "docker-compose", "next_action": "Install Docker Compose and make docker-compose available on PATH."},
        ) from exc
    if compose.returncode != 0:
        raise DemoContractError(
            "Docker Compose is unavailable",
            code="CX_DEMO_COMPOSE_UNAVAILABLE",
            structured_data={"requirement": "docker-compose", "next_action": f"Repair the Docker Compose installation, then rerun {retry_command}."},
        )
    return {"docker": docker.stdout.strip(), "docker_compose": compose.stdout.strip()}


def full_stack_preflight(
    source: Path,
    pricing_snapshot: Path,
    *,
    release_commit: str,
    source_revision: str,
    source_repository: str | None = None,
    source_path: str = ".runtime/cortrix-src",
    secret_env: str = "DEEPSEEK_API_KEY",
    reviewed_attempt_limit: int = 2,
    budget_usd: float = 1.0,
) -> dict[str, Any]:
    if reviewed_attempt_limit not in REVIEWED_ATTEMPT_LIMITS:
        raise DemoContractError("The reviewed Full Stack attempt limit must be 2, 3, 4, or 5")
    require_api_key(secret_env)
    return {
        "secret_present": True,
        "secret_env": secret_env,
        "secret_value_recorded": False,
        "source": verify_source(
            source,
            release_commit=release_commit,
            source_revision=source_revision,
            source_repository=source_repository,
            source_path=source_path,
        ),
        "runtime": verify_runtime(),
        "pricing": verify_pricing_snapshot(pricing_snapshot),
        "budget_usd": budget_usd,
        "max_full_stack_attempts": reviewed_attempt_limit,
        "local_generative_llm": False,
    }


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()
