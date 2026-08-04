from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .errors import DemoContractError


CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
PRIVATE_PATTERNS = {
    "/" + "Users/": "local absolute path",
    "Cortrix" + "GTM": "private control-plane name",
    "project" + "-ops/": "private control-plane path",
    "docs/" + "agentic/": "internal agentic path",
    "-----BEGIN " + "PRIVATE KEY-----": "private-key marker",
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----": "private-key marker",
}
SECRET_ASSIGNMENT = re.compile(r"(?:DEEPSEEK_API_KEY|OPENAI_API_KEY|API_KEY)\s*[:=]\s*[\"']?(?![<$({])[A-Za-z0-9_\-]{12,}")
TEXT_SUFFIXES = {"", ".c", ".cc", ".cpp", ".css", ".h", ".html", ".ini", ".js", ".json", ".md", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml"}


def repository_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    paths = [item for item in result.stdout.decode("utf-8").split("\0") if item]
    return [root / item for item in paths]


def scan_public_safety(root: Path) -> list[str]:
    failures: list[str] = []
    license_path = root / "LICENSE"
    if not license_path.is_file():
        failures.append("The root LICENSE must contain Apache License 2.0")
    else:
        license_text = license_path.read_text(encoding="utf-8")
        if "Apache License" not in license_text or "Version 2.0" not in license_text:
            failures.append("The root LICENSE must contain Apache License 2.0")
    if not (root / "NOTICE").is_file():
        failures.append("The root NOTICE file is required")
    workflows = root / ".github" / "workflows"
    if workflows.exists() and any(path.suffix in {".yml", ".yaml"} for path in workflows.rglob("*")):
        failures.append("GitHub Actions workflows are not allowed in the initial bootstrap")
    for path in repository_files(root):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(root)
        failures.extend(scan_text(text, relative))
    return failures


def scan_text(text: str, relative: Path) -> list[str]:
    failures: list[str] = []
    if CJK_PATTERN.search(text):
        failures.append(f"CJK text is not allowed on main: {relative}")
    for pattern, label in PRIVATE_PATTERNS.items():
        if pattern in text:
            failures.append(f"Found {label} in {relative}")
    if SECRET_ASSIGNMENT.search(text):
        failures.append(f"Found a secret-like assignment in {relative}")
    return failures


def require_safe(root: Path) -> None:
    failures = scan_public_safety(root)
    if failures:
        raise DemoContractError("Public-safety validation failed:\n- " + "\n- ".join(failures))
