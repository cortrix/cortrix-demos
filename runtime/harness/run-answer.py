#!/usr/bin/env python3
"""Run one shared answer prompt through the pinned DeepSeek Harness headless profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


EXPECTED_HARNESS_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
EXPECTED_MODEL = "deepseek-v4-flash"
EXPECTED_BASE_URL = "https://api.deepseek.com/v1"
DURABLE_SESSION_ARTIFACT = "deepseek-harness-session-jsonl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(root: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True).stdout.strip()


def require_harness(root: Path) -> Path:
    if git_output(root, "rev-parse", "HEAD") != EXPECTED_HARNESS_COMMIT:
        raise RuntimeError("DeepSeek Harness checkout does not match the frozen commit")
    if git_output(root, "status", "--short", "--untracked-files=all"):
        raise RuntimeError("DeepSeek Harness checkout is not clean")
    binary = root / "apps" / "cli" / "lib" / "bin.js"
    if not binary.is_file():
        raise RuntimeError("DeepSeek Harness headless binary is unavailable")
    return binary


def write_home_patch(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    patch = """# Local evidence patch: bounded answer calls, inspectable sessions, and no title call.\n- id: llm-deepseek\n  config:\n    apiKeyEnv: DEEPSEEK_API_KEY\n    baseURL: https://api.deepseek.com\n    thinking: disabled\n    reasoningEffort: off\n    maxTokens: 2048\n- id: session-title-llm\n  disabled: true\n- id: session-persistence-jsonl\n  config:\n    root: !!js dshHomePath('sessions')\n    compression: none\n    packChunks: false\n"""
    (home / "cordis.patch.yml").write_text(patch, encoding="utf-8")


def session_files(home: Path) -> set[Path]:
    return {path.resolve() for path in (home / "sessions").rglob("session.jsonl")} if (home / "sessions").exists() else set()


def read_events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if isinstance(value, dict) and value.get("type"):
            events.append(value)
    return events


def usage_projection(events: list[dict[str, Any]]) -> dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0, "cache_hit_tokens": 0, "reasoning_tokens": 0}
    messages = 0
    for event in events:
        if event.get("type") != "assistant/message" or not isinstance(event.get("data"), dict):
            continue
        usage = event["data"].get("usage")
        if not isinstance(usage, dict):
            continue
        messages += 1
        for source, target in (("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"), ("cacheHitTokens", "cache_hit_tokens"), ("reasoningTokens", "reasoning_tokens")):
            value = usage.get(source, 0)
            if isinstance(value, int) and value >= 0:
                total[target] += value
    return {**total, "observable_usage_records": messages}


def sanitize_message(value: str, paths: list[Path], secret: str) -> str:
    result = value.replace(secret, "[redacted]") if secret else value
    for path in sorted(paths, key=lambda item: len(str(item)), reverse=True):
        result = result.replace(str(path), "[local-path]")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one prompt through pinned DeepSeek Harness.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--harness-root", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--usage", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "packages" / "runner" / "src"))
    from cortrix_demo_runner.secret_profile import resolve_secret

    secret = ""
    try:
        binary = require_harness(args.harness_root.resolve())
        prompt = args.prompt.resolve().read_text(encoding="utf-8").strip()
        if not prompt:
            raise RuntimeError("answer prompt is empty")
        home = args.home.resolve()
        write_home_patch(home)
        before = session_files(home)
        resolution = resolve_secret("DEEPSEEK_API_KEY", expected_model=EXPECTED_MODEL, expected_base_url=EXPECTED_BASE_URL)
        secret = resolution.value
        environment = os.environ.copy()
        environment.update({
            "DSH_HOME": str(home),
            "DSH_PERMISSION_MODE": "read-only",
            "DSH_TELEMETRY_DISABLED": "1",
            "DEEPSEEK_API_KEY": secret,
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        })
        completed = subprocess.run(
            ["node", str(binary), "--profile", "headless", prompt],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=600,
            check=False,
        )
        if completed.returncode != 0:
            stderr = sanitize_message(completed.stderr.strip(), [root, args.harness_root.resolve(), home], secret)
            raise RuntimeError(f"DeepSeek Harness headless run failed: {stderr or 'no diagnostic text'}")
        after = session_files(home)
        created = sorted(after - before, key=lambda path: path.stat().st_mtime_ns)
        if len(created) != 1:
            raise RuntimeError("DeepSeek Harness did not create exactly one new durable session artifact")
        events = read_events(created[0])
        usage = usage_projection(events)
        if usage["observable_usage_records"] < 1 or usage["input_tokens"] < 1 or usage["output_tokens"] < 1:
            raise RuntimeError("DeepSeek Harness durable session has no observable token usage")
        args.answer.parent.mkdir(parents=True, exist_ok=True)
        args.usage.parent.mkdir(parents=True, exist_ok=True)
        args.answer.write_text(completed.stdout.strip() + "\n", encoding="utf-8")
        evidence = {
            "schema_version": 1,
            "provider": "deepseek",
            "model": EXPECTED_MODEL,
            "harness_commit": EXPECTED_HARNESS_COMMIT,
            "call_count": 1,
            **usage,
            "secret_source": resolution.source,
            "secret_value_recorded": False,
            "fallback_used": False,
            "local_generative_llm": False,
            # The raw session stays in ignored runtime storage. Curated usage exposes
            # only a stable kind label and content digest, never a path-derived identity.
            "durable_session_artifact": DURABLE_SESSION_ARTIFACT,
            "durable_session_sha256": sha256(created[0]),
            "prompt_sha256": sha256(args.prompt.resolve()),
            "answer_sha256": sha256(args.answer.resolve()),
        }
        args.usage.write_text(json.dumps(evidence, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "pass", "provider": "deepseek", "model": EXPECTED_MODEL, "call_count": 1, "secret_source": resolution.source, "secret_value_recorded": False}, ensure_ascii=True))
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        message = sanitize_message(str(exc), [root, args.harness_root.resolve(), args.home.resolve()], secret)
        print(json.dumps({"error": {"code": "CX_DEMO_HARNESS_ANSWER_FAILED", "category": "permanent", "retryable": False, "message": message, "structured_data": {"external_call_may_have_occurred": True}}}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
