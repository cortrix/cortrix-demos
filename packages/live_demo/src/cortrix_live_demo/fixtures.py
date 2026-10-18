"""Load the frozen public en-US fixtures without performing runtime operations."""

from __future__ import annotations

from pathlib import Path

from .contracts import read_fixture_bytes, validate_fixture_set


QUESTION_CONTRACT = "order_api_create_request/v2"


def question(fixtures_root: Path | str) -> str:
    root = Path(fixtures_root).resolve()
    validate_fixture_set(root)
    manifest = validate_fixture_set(root)
    raw = read_fixture_bytes(root / manifest["query"]["path"], manifest["query"]["sha256"])
    return raw.decode("utf-8").strip()


def seed(state, fixture_root: Path | str) -> None:
    root = Path(fixture_root).resolve()
    manifest = validate_fixture_set(root)
    for item in manifest["documents"]:
        path = (root / item["path"]).resolve()
        original = read_fixture_bytes(path, item["sha256"])
        metadata = {key: item[key] for key in ("document_id", "version", "status", "effective_at")}
        state.add_file(item["path"], original, {**metadata, "default": True, "locale": "en-US", "synthetic": True})
