from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from .errors import DemoContractError
from .io import read_json, sha256_file, write_json
from .secret_profile import resolve_secret


ROOT = Path(__file__).resolve().parents[4]
COMPOSE_PROJECT = "cortrix_demos_order_api"
COMPOSE_FILE = ROOT / "runtime" / "docker-compose.yml"
API_BASE = "http://127.0.0.1:18420/api/v1"
IMAGE_PROVENANCE_PATH = ROOT / "runtime" / "image-provenance.json"
SUCCESS_STATES = {"ready", "completed", "success", "succeeded"}
FAILURE_STATES = {"failed", "cancelled", "canceled", "error"}
LLM_SECRET_ENV = "DEEPSEEK_API_KEY"
LLM_MODEL = "deepseek-v4-flash"
LLM_BASE_URL = "https://api.deepseek.com/v1"


def _http_status_error(operation: str, status: int) -> DemoContractError:
    data = {"operation": operation, "http_status": status}
    if status == 429:
        return DemoContractError(
            f"{operation} returned HTTP 429",
            code="CX_DEMO_HTTP_RATE_LIMITED",
            category="quota",
            retryable=True,
            retry_after_ms=1000,
            structured_data=data,
        )
    if 500 <= status <= 599:
        return DemoContractError(
            f"{operation} returned HTTP {status}",
            code="CX_DEMO_HTTP_SERVER_ERROR",
            category="transient",
            retryable=True,
            retry_after_ms=1000,
            structured_data=data,
        )
    return DemoContractError(
        f"{operation} returned HTTP {status}",
        code="CX_DEMO_HTTP_STATUS_UNEXPECTED",
        structured_data=data,
    )


def _timeout_error(operation: str, timeout_seconds: float) -> DemoContractError:
    return DemoContractError(
        f"{operation} timed out",
        code="CX_DEMO_OPERATION_TIMEOUT",
        category="timeout",
        retryable=True,
        retry_after_ms=1000,
        structured_data={"operation": operation, "timeout_seconds": timeout_seconds},
    )


def _connection_error(operation: str) -> DemoContractError:
    return DemoContractError(
        f"{operation} failed before an HTTP response",
        code="CX_DEMO_HTTP_CONNECTION_FAILED",
        structured_data={
            "operation": operation,
            "next_action": "Check the required local or provider network endpoint before starting another reviewed attempt.",
        },
    )


def compose_environment(profile: str) -> dict[str, str]:
    environment = os.environ.copy()
    if profile == "full-stack":
        api_key = require_key()
        environment.update(
            {
                "CORTRIX_LLM_ENABLED": "true",
                "CORTRIX_LLM_PROVIDER": "deepseek",
                "CORTRIX_LLM_API_KEY": api_key,
                "CORTRIX_LLM_MODEL": "deepseek-v4-flash",
                "CORTRIX_LLM_BASE_URL": "https://api.deepseek.com/v1",
            }
        )
    else:
        environment["CORTRIX_LLM_ENABLED"] = "false"
    return environment


def require_key() -> str:
    return resolve_secret(
        LLM_SECRET_ENV,
        expected_model=LLM_MODEL,
        expected_base_url=LLM_BASE_URL,
    ).value


def compose(arguments: list[str], profile: str = "embedding-only", capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker-compose", "-p", COMPOSE_PROJECT, "-f", str(COMPOSE_FILE), *arguments],
        cwd=ROOT,
        env=compose_environment(profile),
        check=True,
        text=True,
        capture_output=capture,
    )


def load_image_provenance() -> dict[str, Any]:
    provenance = read_json(IMAGE_PROVENANCE_PATH)
    required_strings = (
        "distribution",
        "image",
        "source_repository",
        "cortrix_release",
        "release_commit",
        "source_revision",
        "dockerfile",
        "source_revision_build_arg",
        "required_oci_revision_label",
    )
    if provenance.get("schema_version") != 1 or any(not isinstance(provenance.get(key), str) or not provenance[key] for key in required_strings):
        raise DemoContractError("Image provenance contract is incomplete")
    if provenance["distribution"] != "local_source_build" or provenance.get("registry_source") is not None:
        raise DemoContractError("Image provenance must use the reviewed local source build distribution")
    compose_text = COMPOSE_FILE.read_text(encoding="utf-8")
    if f"image: {provenance['image']}" not in compose_text:
        raise DemoContractError("Compose image does not match the image provenance contract")
    if f"CORTRIX_SOURCE_REVISION: {provenance['source_revision']}" not in compose_text:
        raise DemoContractError("Compose source revision does not match the image provenance contract")
    return provenance


def require_scenario_image_provenance(requires: dict[str, Any]) -> dict[str, Any]:
    provenance = load_image_provenance()
    expected = {
        "cortrix_release": requires.get("cortrix_release"),
        "release_commit": requires.get("cortrix_release_commit"),
        "source_revision": requires.get("cortrix_source_revision"),
    }
    if any(provenance.get(key) != value for key, value in expected.items()):
        raise DemoContractError(
            "Scenario source identity does not match the image provenance contract",
            code="CX_DEMO_IMAGE_PROVENANCE_MISMATCH",
            structured_data={"next_action": "Align the scenario source requirements, image provenance manifest, and Compose runtime before preparing or running the image."},
        )
    return provenance


def ensure_image(source: Path, *, build_if_missing: bool = False) -> dict[str, str]:
    provenance = load_image_provenance()
    image_name = provenance["image"]
    source_revision = provenance["source_revision"]
    dockerfile = source / provenance["dockerfile"]
    found = subprocess.run(["docker", "image", "inspect", image_name], capture_output=True, text=True, check=False)
    action = "reused"
    if found.returncode != 0:
        if not build_if_missing:
            raise DemoContractError(
                "Pinned Cortrix image is missing",
                code="CX_DEMO_IMAGE_MISSING",
                structured_data={"image": image_name, "next_action": "Run ./democtl prepare-image for the selected scenario before live execution."},
            )
        action = "built"
        subprocess.run(
            [
                "docker",
                "build",
                "--tag",
                image_name,
                "--file",
                str(dockerfile),
                "--build-arg",
                f"{provenance['source_revision_build_arg']}={source_revision}",
                str(source),
            ],
            check=True,
        )
    inspect = subprocess.run(
        ["docker", "image", "inspect", image_name, "--format", f"{{{{.Id}}}} {{{{index .Config.Labels \"{provenance['required_oci_revision_label']}\"}}}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split()
    if len(inspect) != 2 or inspect[1] != source_revision:
        raise DemoContractError(
            "Cortrix container image source revision is missing or mismatched",
            code="CX_DEMO_IMAGE_REVISION_MISMATCH",
            structured_data={"image": image_name, "expected_revision": source_revision, "next_action": "Remove or retag the mismatched local image, then run democtl prepare-image from the pinned source checkout."},
        )
    return {
        "image": image_name,
        "digest": inspect[0],
        "source_revision": inspect[1],
        "distribution": provenance["distribution"],
        "source_repository": provenance["source_repository"],
        "dockerfile": provenance["dockerfile"],
        "action": action,
    }


def materialize_config(profile: str) -> Path:
    source = ROOT / "runtime" / "config" / f"cortrix.{profile}.yaml"
    text = source.read_text(encoding="utf-8")
    if profile == "full-stack":
        placeholder = "__RUNTIME_API_KEY__"
        if text.count(placeholder) != 3:
            raise DemoContractError("Tracked Full Stack config must contain exactly three API key placeholders")
        text = text.replace(placeholder, require_key())
    target = ROOT / ".runtime" / "config" / "cortrix.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    target.chmod(0o600)
    return target


def ensure_postgres_schema(timeout_seconds: float = 60) -> None:
    readiness_command = [
        "docker-compose",
        "-p",
        COMPOSE_PROJECT,
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "postgres",
        "pg_isready",
        "-U",
        "cortrix_demo",
        "-d",
        "cortrix_demo",
    ]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        ready = subprocess.run(readiness_command, cwd=ROOT, capture_output=True, text=True, check=False)
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise _timeout_error("PostgreSQL readiness", timeout_seconds)
    try:
        compose(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-X",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "cortrix_demo",
                "-d",
                "cortrix_demo",
                "-f",
                "/docker-entrypoint-initdb.d/10-demo.sql",
            ]
        )
    except subprocess.CalledProcessError as exc:
        raise DemoContractError(
            "PostgreSQL demo schema initialization failed",
            code="CX_DEMO_POSTGRES_SCHEMA_FAILED",
            structured_data={"next_action": "Inspect the local PostgreSQL demo volume and rerun after restoring the tracked schema contract."},
        ) from exc


def start(profile: str, timeout_seconds: float = 1800) -> dict[str, Any]:
    materialize_config(profile)
    compose(["up", "-d", "postgres"], profile=profile)
    # The official PostgreSQL image runs init scripts only for a new empty
    # volume. Reapply the idempotent tracked schema for reused demo volumes.
    ensure_postgres_schema()
    compose(["up", "-d", "--force-recreate", "cortrix"], profile=profile)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            _, health = request("GET", "/system/health/ready", timeout=10)
            if isinstance(health, dict):
                return health
        except (DemoContractError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise _timeout_error("Cortrix readiness", timeout_seconds)


def request(method: str, path: str, payload: dict[str, Any] | None = None, expected: set[int] | None = None, timeout: float = 180) -> tuple[int, Any]:
    operation_name = f"{method} {path}"
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    operation = urllib.request.Request(API_BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(operation, timeout=timeout) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
    except http.client.RemoteDisconnected as exc:
        raise _connection_error(operation_name) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise _timeout_error(operation_name, timeout) from exc
        raise _connection_error(operation_name) from exc
    try:
        value = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        value = {"non_json_response": True}
    if status not in (expected or {200}):
        raise _http_status_error(operation_name, status)
    return status, value


def ensure_namespace(name: str) -> None:
    status, _ = request("GET", "/namespaces/" + urllib.parse.quote(name), expected={200, 404})
    if status == 404:
        request("POST", "/namespaces", {"name": name, "display_name": name}, expected={201})


def upload(namespace: str, filename: str, content: str, metadata: dict[str, Any], timeout_seconds: float = 900) -> dict[str, Any]:
    _, accepted = request("POST", "/documents", {"namespace": namespace, "filename": filename, "content": content, "metadata": metadata}, expected={202})
    task_id = accepted.get("task_id") if isinstance(accepted, dict) else None
    if not isinstance(task_id, str):
        raise DemoContractError("Document upload did not return a task ID")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        _, progress = request("GET", "/documents/tasks/" + urllib.parse.quote(task_id) + "/progress")
        status = progress.get("status", "").lower() if isinstance(progress, dict) else ""
        if status in SUCCESS_STATES:
            if progress.get("error_code") or progress.get("error_msg"):
                raise DemoContractError("Document task completed with an error field")
            return progress
        if status in FAILURE_STATES:
            raise DemoContractError("Document task entered a failure state")
        time.sleep(1)
    raise _timeout_error("Document ingestion", timeout_seconds)


def metrics() -> str:
    result = compose(["exec", "-T", "cortrix", "curl", "-fsS", "http://127.0.0.1:9091/metrics"], capture=True)
    return result.stdout


def parse_metrics(text: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            name, value = line.rsplit(" ", 1)
            result[name] = float(value)
        except ValueError:
            continue
    return result


def metric_delta(before: dict[str, float], after: dict[str, float], name: str) -> float:
    return after.get(name, 0) - before.get(name, 0)


def inspect_namespace(namespace: str) -> dict[str, Any]:
    result = compose(
        ["exec", "-T", "cortrix", "python3", "/demo-helpers/inspect_namespace.py", "--db", f"/data/units/unit-{namespace}/store.db"],
        capture=True,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise DemoContractError("Durable namespace inspection is not an object")
    return value


def verify_models() -> dict[str, Any]:
    manifest = read_json(ROOT / "runtime" / "model-manifest.json")
    results = []
    for asset in manifest["assets"]:
        command = ["exec", "-T", "cortrix", "sha256sum", asset["container_path"]]
        actual = compose(command, capture=True).stdout.split()[0]
        results.append({"component": asset["component"], "model": asset["model"], "sha256": actual, "match": actual == asset["sha256"]})
    if not all(item["match"] for item in results):
        raise DemoContractError("One or more runtime model checksums failed")
    return {"schema_version": 1, "all_match": True, "assets": results}


def contract_smoke() -> dict[str, Any]:
    payload = {"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 2, "temperature": 0}
    operation = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + require_key(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(operation, timeout=60) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _http_status_error("DeepSeek contract smoke", exc.code) from exc
    except TimeoutError as exc:
        raise _timeout_error("DeepSeek contract smoke", 60) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise _timeout_error("DeepSeek contract smoke", 60) from exc
        raise _connection_error("DeepSeek contract smoke") from exc
    if value.get("model") != "deepseek-v4-flash":
        raise DemoContractError("DeepSeek contract smoke returned a different model identity")
    usage = value.get("usage") if isinstance(value.get("usage"), dict) else {}
    return {"provider": "deepseek", "model": value.get("model"), "call_count": 1, "usage": usage, "response_content_recorded": False}


def identity_map(durable: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        str(item["child_id"]): {"document_id": str(item["document_id"]), "doc_id": str(item["doc_id"])}
        for item in durable.get("text_blocks", [])
        if item.get("child_id") and item.get("document_id") and item.get("doc_id")
    }


def sanitized_runtime(run_id: str, health: dict[str, Any], image: dict[str, str]) -> dict[str, Any]:
    services_raw = compose(["ps", "--format", "json"], capture=True).stdout
    services = []
    for line in services_raw.splitlines():
        if line.strip():
            item = json.loads(line)
            services.append({key: item.get(key) for key in ("Name", "Image", "Service", "Project", "State", "Health", "Status", "Ports")})
    return {
        "schema_version": 1,
        "run_id": run_id,
        "health": health,
        "image": image,
        "services": services,
        "llm": {"provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/v1", "local_generative_llm": False, "secret_persisted_in_evidence": False},
    }


def cleanup(run_id: str, receipt: Path) -> dict[str, Any]:
    suffix = safe_run_suffix(run_id)
    namespaces = [f"order-b-{suffix}", f"order-a-docs-{suffix}", f"order-a-query-{suffix}"]
    namespace_result = {"namespaces": [], "all_removed": False}
    running = subprocess.run(
        ["docker-compose", "-p", COMPOSE_PROJECT, "-f", str(COMPOSE_FILE), "ps", "-q", "cortrix"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if running.stdout.strip():
        raw = compose(["exec", "-T", "cortrix", "python3", "/demo-helpers/cleanup_namespaces.py", *namespaces], capture=True).stdout
        namespace_result = json.loads(raw)
    compose(["down", "--remove-orphans"])
    runtime_config = ROOT / ".runtime" / "config" / "cortrix.yaml"
    runtime_secret_removed = runtime_config.exists()
    runtime_config.unlink(missing_ok=True)
    listeners = {}
    for port in (18420, 19091, 15432):
        result = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True, check=False)
        listeners[str(port)] = bool(result.stdout.strip())
    result = {"schema_version": 1, "run_id": run_id, "namespaces": namespace_result["namespaces"], "namespaces_removed": namespace_result["all_removed"], "containers_removed": True, "ports_released": not any(listeners.values()), "runtime_secret_removed": runtime_secret_removed, "model_cache_preserved": True, "docker_volumes_preserved": True}
    write_json(receipt, result)
    return result


def verify_fixture_hashes(fixtures: Path, manifest: dict[str, Any]) -> None:
    for item in [manifest["query"], *manifest["documents"]]:
        if sha256_file(fixtures / item["path"]) != item["sha256"]:
            raise DemoContractError("Fixture checksum changed after preflight")


def safe_run_suffix(run_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", run_id.lower()).strip("-")[-24:]
