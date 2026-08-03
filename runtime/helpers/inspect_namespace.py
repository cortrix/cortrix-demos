#!/usr/bin/env python3
"""Inspect durable Cortrix identity and enrichment state as JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3


TEXT_BLOCK = 1
HYPE_BLOCK = 16
DOC_SUMMARY_BLOCK = 17


def parse_object(value: str | None) -> dict:
    parsed = json.loads(value or "{}")
    return parsed if isinstance(parsed, dict) else {}


def inspect_database(path: Path) -> dict:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        documents = []
        document_id_by_doc_id = {}
        for doc_id, source_path, metadata_json, status in connection.execute(
            "SELECT doc_id, source_path, metadata_json, status FROM documents ORDER BY doc_id"
        ):
            metadata = parse_object(metadata_json)
            document_id_by_doc_id[doc_id] = metadata.get("document_id")
            documents.append({"doc_id": doc_id, "document_id": metadata.get("document_id"), "source_path": source_path, "status": status})
        text_blocks = [
            {
                "child_id": child_id,
                "doc_id": doc_id,
                "document_id": document_id_by_doc_id.get(doc_id),
                "chunk_index": chunk_index,
                "content": content,
                "contextualized_status": contextualized_status,
            }
            for child_id, doc_id, chunk_index, content, contextualized_status in connection.execute(
                "SELECT child_id, doc_id, chunk_index, content_text, contextualized_status FROM blocks WHERE block_type = ? ORDER BY doc_id, chunk_index, block_id",
                (TEXT_BLOCK,),
            )
        ]
        block_counts = {
            str(block_type): count
            for block_type, count in connection.execute("SELECT block_type, COUNT(*) FROM blocks GROUP BY block_type")
        }
        enrich_states = [
            {"child_id": child_id, "doc_id": doc_id, "status": status, "attempts": attempts, "last_error": last_error}
            for child_id, doc_id, status, attempts, last_error in connection.execute(
                "SELECT child_id, doc_id, status, attempts, last_error FROM enrich_state ORDER BY doc_id, child_id"
            )
        ]
    finally:
        connection.close()
    return {
        "schema_version": 1,
        "documents": documents,
        "text_blocks": text_blocks,
        "block_counts": block_counts,
        "enrich_state_ok_count": sum(item["status"] == "ok" for item in enrich_states),
        "hype_question_count": int(block_counts.get(str(HYPE_BLOCK), 0)),
        "document_summary_count": int(block_counts.get(str(DOC_SUMMARY_BLOCK), 0)),
        "enrich_states": enrich_states,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect_database(args.db), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
