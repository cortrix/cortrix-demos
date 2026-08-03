from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import DemoContractError


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoContractError(f"Cannot read JSON object from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DemoContractError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: object, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DemoContractError(f"Cannot hash {path}: {exc}") from exc
    return digest.hexdigest()
