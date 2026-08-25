from __future__ import annotations

from pathlib import Path
import subprocess

from .errors import DemoContractError
from .safety import TEXT_SUFFIXES, scan_text


def _git(root: Path, *args: str, text: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=text)


def verify_public_history(root: Path, base_ref: str) -> dict[str, object]:
    base = _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}", text=True).stdout.strip()
    head = _git(root, "rev-parse", "HEAD", text=True).stdout.strip()
    commits = [line for line in _git(root, "rev-list", "--reverse", f"{base}..{head}", text=True).stdout.splitlines() if line]
    if not commits:
        raise DemoContractError("Public history scan requires at least one commit after the base ref")

    failures: list[str] = []
    scanned_files = 0
    for commit in commits:
        message = _git(root, "show", "-s", "--format=%an%n%ae%n%s%n%b", commit, text=True).stdout
        for failure in scan_text(message, Path("git-metadata.txt")):
            failures.append(f"{commit}: {failure}")
        names = _git(root, "ls-tree", "-r", "--name-only", "-z", commit).stdout.decode("utf-8").split("\0")
        for name in (item for item in names if item):
            relative = Path(name)
            if relative.suffix.lower() not in TEXT_SUFFIXES:
                continue
            content = _git(root, "show", f"{commit}:{name}").stdout
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                continue
            scanned_files += 1
            for failure in scan_text(text, relative):
                failures.append(f"{commit}:{name}: {failure}")

    if failures:
        raise DemoContractError("Public history validation failed:\n- " + "\n- ".join(failures))
    return {"status": "pass", "base_commit": base, "head_commit": head, "commits_scanned": len(commits), "text_files_scanned": scanned_files, "external_calls": 0}
