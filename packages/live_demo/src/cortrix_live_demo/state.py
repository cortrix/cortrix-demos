"""Durable state, explicit external-call authorization, and conservative budgets."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import uuid

from .config import RuntimeConfig


RUN_LIMITS = {"deterministic": 4, "harness": 6}
HARNESS_REQUEST_LIMIT = 48
EXECUTION_CONTRACT = "live_three_path/v1"


def stamp() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic(path: Path | str, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".pending")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class Paused(RuntimeError):
    """Execution stopped at a durable boundary and may require operator action."""


class State:
    def __init__(self, root: Path | str, config: RuntimeConfig):
        self.root = Path(root).resolve()
        self.config = config
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.path = self.root / "workspace.json"
        policy = {
            "caps": {
                "total": config.budget_total_usd,
                "deterministic": config.budget_deterministic_usd,
                "harness": config.budget_harness_usd,
            },
            "pricing": {
                "model": config.provider_model,
                "input_cache_hit": config.provider_input_cache_hit_usd_per_million,
                "input_cache_miss": config.provider_input_cache_miss_usd_per_million,
                "output": config.provider_output_usd_per_million,
                "basis": "operator_configured_upper_bound",
            },
        }
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if self.data.get("policy") != policy:
                raise Paused("CORTRIX_LIVE_DEMO_POLICY_CHANGED")
        else:
            self.data = {
                "schema": "cortrix_live_demo_workspace/v1",
                "files": [],
                "runs": [],
                "current_run_id": None,
                "requests": [],
                "policy": policy,
            }

    def save(self) -> None:
        with self.lock:
            atomic(self.path, self.data)

    def add_file(self, name: str, raw: bytes, metadata: dict | None = None) -> dict:
        if not isinstance(name, str) or not name or name in {".", ".."} or any(character in name for character in "/\\\x00") or any(ord(character) < 32 for character in name):
            raise ValueError("Invalid file name")
        if not raw or len(raw) > 2 * 1024 * 1024:
            raise ValueError("A file must contain 1 byte to 2 MiB")
        content = raw.decode("utf-8", errors="strict")
        if "\x00" in content or not content.strip():
            raise ValueError("Only nonempty UTF-8 text is supported")
        if name.lower().endswith(".json"):
            json.loads(content)
        if name.lower().endswith((".zip", ".pdf", ".docx", ".png", ".jpg", ".exe")):
            raise ValueError("This file format is not supported")
        sha256 = digest(raw)
        with self.lock:
            existing = next((item for item in self.data["files"] if item["sha256"] == sha256 and item["name"] == name), None)
            if existing:
                return existing
            item = {
                "id": "file_" + digest(name.encode() + raw)[:20],
                "name": name,
                "bytes": len(raw),
                "sha256": sha256,
                "content": content,
                "locale": "en-US",
                "default": False,
                "status": "unknown",
                "version": "unknown",
                "effective_at": "",
                "created_at": stamp(),
            }
            item.update(metadata or {})
            item.setdefault("document_id", item["id"])
            atomic(self.root / "originals" / (item["id"] + ".json"), item)
            self.data["files"].append(item)
            self.save()
            return item

    def run_path(self, run_id: str) -> Path:
        if not re.fullmatch(r"run_[0-9a-f]{16}", run_id):
            raise ValueError("Invalid run identity")
        return self.root / "runs" / run_id

    def get(self, run_id: str) -> dict:
        return json.loads((self.run_path(run_id) / "run.json").read_text())

    def put(self, run: dict) -> None:
        with self.lock:
            atomic(self.run_path(run["id"]) / "run.json", run)
            for index, item in enumerate(self.data["runs"]):
                if item["id"] == run["id"]:
                    self.data["runs"][index] = {key: run[key] for key in ("id", "mode", "locale", "state", "created_at")}
            self.save()

    def run_allowance(self) -> dict:
        return {
            mode: {"used": sum(run["mode"] == mode for run in self.data["runs"]), "limit": limit}
            for mode, limit in RUN_LIMITS.items()
        }

    def create(self, payload: dict) -> tuple[dict, bool]:
        with self.lock:
            key = payload.get("idempotency_key")
            if not isinstance(key, str) or not 8 <= len(key) <= 200:
                raise ValueError("An idempotency key is required")
            body_hash = digest(json.dumps({name: value for name, value in payload.items() if name != "idempotency_key"}, sort_keys=True).encode())
            for item in self.data["runs"]:
                prior = self.get(item["id"])
                if prior["idempotency_key"] == key:
                    if prior["request_hash"] != body_hash:
                        raise ValueError("The idempotency key conflicts with another input")
                    return prior, False
            if any(item["state"] in {"running", "queued", "cancelling", "cleaning"} for item in self.data["runs"]):
                raise ValueError("Another run is active")
            if any(item["state"] not in {"completed", "cleaned"} for item in self.data["runs"]):
                raise Paused("CORTRIX_LIVE_DEMO_PRIOR_RUN_UNRESOLVED")
            mode = payload.get("mode", "deterministic")
            locale = payload.get("locale", "en-US")
            if mode not in {"deterministic", "harness"} or locale != "en-US":
                raise ValueError("Only deterministic or harness mode with en-US inputs is supported")
            if sum(item["mode"] == mode for item in self.data["runs"]) >= RUN_LIMITS[mode]:
                raise Paused("CORTRIX_LIVE_DEMO_RUN_LIMIT")
            identifiers = payload.get("input_ids", [])
            files = [item for item in self.data["files"] if item["id"] in identifiers]
            if not identifiers or len(set(identifiers)) != len(identifiers) or len(files) != len(identifiers) or len(files) > 8:
                raise ValueError("Select 1 to 8 distinct known files")
            if sum(item["bytes"] for item in files) > 8 * 1024 * 1024 or len({item["name"] for item in files}) != len(files):
                raise ValueError("The combined input exceeds 8 MiB or has duplicate names")
            if len({item["document_id"] for item in files}) != len(files):
                raise ValueError("Duplicate document identities are not allowed")
            if payload.get("external_call_authorized") is not True:
                raise ValueError("Explicit authorization for external model calls is required")
            question = payload.get("question", "").strip()
            if not question or len(question.encode()) > 8192:
                raise ValueError("The question must contain 1 to 8192 UTF-8 bytes")
            run_id = "run_" + uuid.uuid4().hex[:16]
            run = {
                "schema": "cortrix_live_demo_run/v1",
                "id": run_id,
                "mode": mode,
                "locale": locale,
                "created_at": stamp(),
                "state": "queued",
                "question": question,
                "files": files,
                "events": [],
                "idempotency_key": key,
                "request_hash": body_hash,
                "cancel_requested": False,
                "paths": {
                    path: {"state": "queued", "steps": [], "result": None, "checkpoint": {}}
                    for path in (["a0", "a1", "b"] if mode == "deterministic" else ["pg", "b"])
                },
                "external_call_authorization": {
                    "accepted": True,
                    "at": stamp(),
                    "provider": self.config.provider_model,
                    "input_hashes": [item["sha256"] for item in files],
                },
                "error": None,
            }
            self.data["runs"].append({key: run[key] for key in ("id", "mode", "locale", "state", "created_at")})
            self.data["current_run_id"] = run_id
            self.put(run)
            return run, True

    def event(self, run_id: str, path: str, stage: str, value: dict) -> dict:
        with self.lock:
            run = self.get(run_id)
            sequence = len(run["events"]) + 1
            event = {
                "sequence": sequence,
                "run_id": run_id,
                "path": path,
                "stage": stage,
                "observed_at": stamp(),
                "state": value.get("state", "failed" if stage.endswith("_failed") else "started" if stage.endswith("_started") else "completed"),
                "duration_ms": value.get("duration_ms"),
                "artifact_ref": f"artifacts/{sequence:04d}-{stage}.json",
            }
            from .event_projection import details
            event.update(details(stage, value))
            atomic(self.run_path(run_id) / event["artifact_ref"], value)
            run["events"].append(event)
            if path in run["paths"]:
                run["paths"][path]["steps"].append(event)
            self.put(run)
            return event

    def budget(self) -> dict:
        with self.lock:
            caps = self.data["policy"]["caps"]
            by_mode = {}
            for mode in ("deterministic", "harness"):
                rows = [row for row in self.data["requests"] if row["mode"] == mode]
                by_mode[mode] = {
                    "estimated_spent_usd": sum(row.get("cost_upper_usd", 0) for row in rows),
                    "reserved_usd": sum(max(row["reserved_usd"] - row.get("cost_upper_usd", 0), 0) for row in rows if row["state"] != "completed"),
                    "limit_usd": caps[mode],
                    "requests": len(rows),
                }
            origins = {
                origin: sum((row.get("origin") or ("harness" if row.get("harness") else "core")) == origin for row in self.data["requests"])
                for origin in ("core", "harness", "application_llm")
            }
            return {
                "spent_usd": sum(value["estimated_spent_usd"] for value in by_mode.values()),
                "reserved_usd": sum(value["reserved_usd"] for value in by_mode.values()),
                "total_limit_usd": caps["total"],
                "actual_cost": "unknown",
                "cost_basis": "operator_configured_upper_bound",
                "by_mode": by_mode,
                "pricing": self.data["policy"]["pricing"],
                "request_origins": origins,
                "harness_direct_requests": sum(bool(row.get("harness")) for row in self.data["requests"]),
            }

    def reserve(self, run_id: str, path: str, request_id: str, payload: dict, harness: bool = False, session_id: str | None = None, *, origin: str | None = None, task: str | None = None, payload_sha256: str | None = None) -> dict:
        with self.lock:
            run = self.get(run_id)
            if run["state"] != "running" or run["cancel_requested"]:
                raise Paused("CORTRIX_LIVE_DEMO_RUN_NOT_ACTIVE")
            if not self.config.allow_external_calls:
                raise Paused("CORTRIX_LIVE_DEMO_EXTERNAL_CALLS_DISABLED")
            if any(item["request_id"] == request_id for item in self.data["requests"]):
                raise Paused("CORTRIX_LIVE_DEMO_REQUEST_ALREADY_RESERVED")
            if payload.get("model") != self.config.provider_model:
                raise ValueError("The request model does not match the configured provider profile")
            maximum_tokens = payload.get("max_tokens", 2048)
            output_cap = 2048 if harness or origin == "application_llm" else 4096
            if not isinstance(maximum_tokens, int) or not 1 <= maximum_tokens <= output_cap:
                raise ValueError("The output exceeds the per-request maximum")
            input_bound = len(json.dumps(payload, ensure_ascii=False).encode()) + 8192
            if input_bound > 128000:
                raise Paused("CORTRIX_LIVE_DEMO_INPUT_LIMIT")
            if harness:
                rows = [item for item in self.data["requests"] if item.get("harness")]
                if len(rows) >= HARNESS_REQUEST_LIMIT or sum(item.get("session_id") == session_id for item in rows) >= 4:
                    raise Paused("CORTRIX_LIVE_DEMO_TURN_LIMIT")
            pricing = self.data["policy"]["pricing"]
            if pricing["input_cache_miss"] is None or pricing["output"] is None:
                raise Paused("CORTRIX_LIVE_DEMO_PRICING_REQUIRED")
            reserved = (input_bound * pricing["input_cache_miss"] + maximum_tokens * pricing["output"]) / 1e6
            budget = self.budget()
            group = budget["by_mode"][run["mode"]]
            if budget["spent_usd"] + budget["reserved_usd"] + reserved > budget["total_limit_usd"] or group["estimated_spent_usd"] + group["reserved_usd"] + reserved > group["limit_usd"]:
                raise Paused("CORTRIX_LIVE_DEMO_BUDGET_PAUSED")
            row = {
                "request_id": request_id,
                "run_id": run_id,
                "path": path,
                "mode": run["mode"],
                "session_id": session_id,
                "harness": harness,
                "reserved_usd": reserved,
                "input_token_upper_bound": input_bound,
                "max_output_tokens": maximum_tokens,
                "state": "reserved",
                "created_at": stamp(),
                "origin": origin,
                "task": task,
                "payload_sha256": payload_sha256,
            }
            self.data["requests"].append(row)
            self.save()
            return row

    def settle(self, request_id: str, usage: dict | None) -> None:
        with self.lock:
            row = next(item for item in self.data["requests"] if item["request_id"] == request_id)
            if not usage or "prompt_tokens" not in usage or "completion_tokens" not in usage:
                row["state"] = "usage_unknown"
                self.save()
                raise Paused("CORTRIX_LIVE_DEMO_USAGE_UNRESOLVED")
            pricing = self.data["policy"]["pricing"]
            if None in (pricing["input_cache_hit"], pricing["input_cache_miss"], pricing["output"]):
                raise Paused("CORTRIX_LIVE_DEMO_PRICING_REQUIRED")
            hit = int(usage.get("prompt_cache_hit_tokens", 0))
            total = int(usage["prompt_tokens"])
            output = int(usage["completion_tokens"])
            if not 0 <= hit <= total or output < 0:
                raise ValueError("Invalid provider usage")
            cost = ((total - hit) * pricing["input_cache_miss"] + hit * pricing["input_cache_hit"] + output * pricing["output"]) / 1e6
            row.update(state="completed", usage=usage, cost_upper_usd=cost, completed_at=stamp())
            if cost > row["reserved_usd"] + 1e-9:
                row["state"] = "reservation_violation"
                self.save()
                raise Paused("CORTRIX_LIVE_DEMO_RESERVATION_VIOLATION")
            self.save()
