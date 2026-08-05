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
PRIVATE_IPV4 = re.compile(r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b")
# Keep the approved local preview address out of tracked text as one literal so
# the scanner can inspect its own source without granting itself a blanket pass.
PREFERRED_LOCAL_PREVIEW_ADDRESS = ".".join(("192", "168", "50", "75"))
ALLOWED_PRIVATE_IPV4 = {Path("Makefile"): {PREFERRED_LOCAL_PREVIEW_ADDRESS}}
TEXT_SUFFIXES = {"", ".c", ".cc", ".cpp", ".css", ".h", ".html", ".ini", ".js", ".json", ".md", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml"}
# Internal feature identifiers are private tracking labels. They must never appear
# in public contracts, output field names, or documentation. Evidence archived under
# a scenario is exempt because a recorded run is never rewritten; the acceptance
# verifier maps the retired names it still contains onto the current ones.
INTERNAL_FEATURE_ID = re.compile(r"\bF\d{2}[a-z]?\b|\bf\d{2}_[a-z]")


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
        if not is_archived_evidence(relative):
            failures.extend(scan_internal_feature_ids(text, relative))
    return failures


def is_archived_evidence(relative: Path) -> bool:
    parts = relative.parts
    return len(parts) > 3 and parts[0] == "scenarios" and parts[2] == "evidence"


def scan_internal_feature_ids(text: str, relative: Path) -> list[str]:
    found = sorted({match.group(0) for match in INTERNAL_FEATURE_ID.finditer(text)})
    return [f"Found an internal feature identifier in {relative}: {name}" for name in found]


def scan_text(text: str, relative: Path) -> list[str]:
    failures: list[str] = []
    if CJK_PATTERN.search(text):
        failures.append(f"CJK text is not allowed on main: {relative}")
    for pattern, label in PRIVATE_PATTERNS.items():
        if pattern in text:
            failures.append(f"Found {label} in {relative}")
    if SECRET_ASSIGNMENT.search(text):
        failures.append(f"Found a secret-like assignment in {relative}")
    allowed = ALLOWED_PRIVATE_IPV4.get(relative, set())
    unexpected_private_ipv4 = sorted({match.group(0) for match in PRIVATE_IPV4.finditer(text)} - allowed)
    for address in unexpected_private_ipv4:
        failures.append(f"Found a private IPv4 literal in {relative}: {address}")
    return failures


def require_safe(root: Path) -> None:
    failures = scan_public_safety(root)
    if failures:
        raise DemoContractError("Public-safety validation failed:\n- " + "\n- ".join(failures))
