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
from .scenario import SOURCE_REVISION


ROOT = Path(__file__).resolve().parents[4]
COMPOSE_PROJECT = "cortrix_demos_order_api"
COMPOSE_FILE = ROOT / "runtime" / "docker-compose.yml"
API_BASE = "http://127.0.0.1:18420/api/v1"
IMAGE = "cortrix-demo:32b82f6"
SUCCESS_STATES = {"ready", "completed", "success", "succeeded"}
FAILURE_STATES = {"failed", "cancelled", "canceled", "error"}


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
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if len(api_key) < 20:
        raise DemoContractError("DEEPSEEK_API_KEY is missing; no external call was made")
    return api_key


def compose(arguments: list[str], profile: str = "embedding-only", capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker-compose", "-p", COMPOSE_PROJECT, "-f", str(COMPOSE_FILE), *arguments],
        cwd=ROOT,
        env=compose_environment(profile),
        check=True,
        text=True,
        capture_output=capture,
    )


def ensure_image(source: Path) -> dict[str, str]:
    found = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, text=True, check=False)
    if found.returncode != 0:
        subprocess.run(
            [
                "docker",
                "build",
                "--tag",
                IMAGE,
                "--file",
                str(source / "deploy" / "Dockerfile"),
                "--build-arg",
                f"CORTRIX_SOURCE_REVISION={SOURCE_REVISION}",
                str(source),
            ],
            check=True,
        )
    inspect = subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}} {{index .Config.Labels \"org.opencontainers.image.revision\"}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split()
    if len(inspect) != 2 or inspect[1] != SOURCE_REVISION:
        raise DemoContractError("Cortrix container image source revision is missing or mismatched")
    return {"image": IMAGE, "digest": inspect[0], "source_revision": inspect[1]}


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


def start(profile: str, timeout_seconds: float = 1800) -> dict[str, Any]:
    materialize_config(profile)
    compose(["up", "-d", "postgres"], profile=profile)
    compose(["up", "-d", "--force-recreate", "cortrix"], profile=profile)
    deadline = time.monotonic() + timeout_seconds
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            _, health = request("GET", "/system/health/ready", timeout=10)
            if isinstance(health, dict):
                return health
        except (DemoContractError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise DemoContractError(f"Cortrix readiness timed out: {last_error}. transient_category=timeout")


def request(method: str, path: str, payload: dict[str, Any] | None = None, expected: set[int] | None = None, timeout: float = 180) -> tuple[int, Any]:
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
        raise DemoContractError(f"{method} {path} closed the connection before an HTTP response") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise DemoContractError(f"{method} {path} timed out. transient_category=timeout") from exc
        raise DemoContractError(f"{method} {path} failed before an HTTP response") from exc
    try:
        value = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        value = {"non_json_response": True}
    if status not in (expected or {200}):
        category = transient_category(status)
        suffix = f" transient_category={category}" if category else ""
        raise DemoContractError(f"{method} {path} returned HTTP {status}.{suffix}")
    return status, value


def transient_category(status: int) -> str | None:
    if status == 429:
        return "http_429"
    if 500 <= status <= 599:
        return "http_5xx"
    return None


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
    raise DemoContractError("Document ingestion timed out. transient_category=timeout")


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
        category = transient_category(exc.code)
        suffix = f" transient_category={category}" if category else ""
        raise DemoContractError(f"DeepSeek contract smoke returned HTTP {exc.code}.{suffix}") from exc
    except TimeoutError as exc:
        raise DemoContractError("DeepSeek contract smoke timed out. transient_category=timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise DemoContractError("DeepSeek contract smoke timed out. transient_category=timeout") from exc
        raise DemoContractError("DeepSeek contract smoke failed before an HTTP response") from exc
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
