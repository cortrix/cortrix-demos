#!/usr/bin/env python3
"""Load one frozen scenario corpus into an isolated Cortrix namespace.

This operator utility deliberately owns namespace and ingestion actions. The
model-visible plugin remains read-only and never receives those capabilities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


SUCCESS_STATES = {"ready", "completed", "success", "succeeded"}
FAILURE_STATES = {"failed", "cancelled", "canceled", "error"}


class RuntimeFailure(RuntimeError):
    """A stable, secret-free runtime failure."""


def request(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None, *, expected: set[int], timeout: float = 180) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=True).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    operation = Request(urljoin(base_url.rstrip("/") + "/", path.lstrip("/")), data=body, headers=headers, method=method)
    try:
        with urlopen(operation, timeout=timeout) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
    except (URLError, TimeoutError) as exc:
        raise RuntimeFailure(f"{method} {path} failed before a valid response") from exc
    try:
        value = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeFailure(f"{method} {path} returned non-JSON content") from exc
    if status not in expected:
        raise RuntimeFailure(f"{method} {path} returned HTTP {status}")
    return status, value


def load_manifest(root: Path, scenario_id: str, position_variant: str | None = None) -> tuple[Path, dict[str, Any]]:
    scenario_root = root / "scenarios" / scenario_id
    manifest_path = scenario_root / "fixtures" / "manifest.json"
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("scenario_id") != scenario_id or not isinstance(value.get("documents"), list):
        raise RuntimeFailure("fixture manifest identity is invalid")
    if position_variant is not None:
        variants_path = scenario_root / "fixtures" / "position-variants.json"
        if not variants_path.is_file():
            raise RuntimeFailure("scenario has no position variants")
        variants = json.loads(variants_path.read_text(encoding="utf-8"))
        selected = next((item for item in variants.get("variants", []) if item.get("id") == position_variant), None)
        document = next((item for item in value["documents"] if item.get("document_id") == variants.get("document_id")), None)
        if not isinstance(selected, dict) or not isinstance(document, dict):
            raise RuntimeFailure("position variant is not frozen")
        document.update({"path": selected["path"], "sha256": selected["sha256"], "version": position_variant})
    for document in value["documents"]:
        path = scenario_root / "fixtures" / document["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != document.get("sha256"):
            raise RuntimeFailure(f"fixture checksum mismatch for {document.get('document_id', 'unknown')}")
    return scenario_root, value


def ensure_namespace(base_url: str, namespace: str) -> None:
    status, _ = request(base_url, "GET", f"api/v1/namespaces/{quote(namespace)}", expected={200, 404})
    if status == 404:
        request(base_url, "POST", "api/v1/namespaces", {"name": namespace, "display_name": namespace}, expected={201})


def upload_document(base_url: str, namespace: str, document: dict[str, Any], content: str, timeout_seconds: float) -> dict[str, Any]:
    _, accepted = request(
        base_url,
        "POST",
        "api/v1/documents",
        {
            "namespace": namespace,
            "filename": document["path"],
            "content": content,
            "metadata": {
                "document_id": document["document_id"],
                "status": document["status"],
                "version": document["version"],
                "source": document["source"],
                "fixture_sha256": document["sha256"],
            },
        },
        expected={202},
    )
    task_id = accepted.get("task_id") if isinstance(accepted, dict) else None
    if not isinstance(task_id, str) or not task_id:
        raise RuntimeFailure("document upload did not return a task_id")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        _, progress = request(base_url, "GET", f"api/v1/documents/tasks/{quote(task_id)}/progress", expected={200})
        state = str(progress.get("status", "")).lower() if isinstance(progress, dict) else ""
        if state in SUCCESS_STATES:
            if progress.get("error_code") or progress.get("error_msg"):
                raise RuntimeFailure("document ingestion completed with an error field")
            return {"document_id": document["document_id"], "task_id": task_id, "status": state}
        if state in FAILURE_STATES:
            raise RuntimeFailure(f"document ingestion failed for {document['document_id']}")
        time.sleep(1)
    raise RuntimeFailure(f"document ingestion timed out for {document['document_id']}")


def cleanup_namespace(base_url: str, namespace: str) -> dict[str, Any]:
    status, _ = request(base_url, "DELETE", f"api/v1/namespaces/{quote(namespace)}", expected={200, 202, 204, 404})
    return {"namespace": namespace, "removed_or_absent": status in {200, 202, 204, 404}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Load or remove one frozen Harness demo corpus.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8420")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--position-variant", choices=("front", "middle", "end"))
    args = parser.parse_args()
    try:
        if args.cleanup:
            result = {"schema_version": 1, "operation": "cleanup", **cleanup_namespace(args.base_url, args.namespace), "external_llm_calls": 0}
        else:
            scenario_root, manifest = load_manifest(args.root.resolve(), args.scenario, args.position_variant)
            ensure_namespace(args.base_url, args.namespace)
            receipts = []
            for document in manifest["documents"]:
                content = (scenario_root / "fixtures" / document["path"]).read_text(encoding="utf-8")
                receipts.append(upload_document(args.base_url, args.namespace, document, content, args.timeout_seconds))
            result = {
                "schema_version": 1,
                "operation": "load",
                "scenario_id": args.scenario,
                "namespace": args.namespace,
                "document_count": len(receipts),
                "documents": receipts,
                "fixture_manifest_sha256": hashlib.sha256((scenario_root / "fixtures" / "manifest.json").read_bytes()).hexdigest(),
                "external_llm_calls": 0,
                **({"position_variant": args.position_variant} if args.position_variant is not None else {}),
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "pass", "operation": result["operation"], "external_llm_calls": 0}, ensure_ascii=True))
        return 0
    except (OSError, RuntimeFailure, json.JSONDecodeError) as exc:
        print(json.dumps({"error": {"code": "CX_DEMO_HARNESS_INGESTION_FAILED", "category": "permanent", "retryable": False, "message": str(exc)}}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
