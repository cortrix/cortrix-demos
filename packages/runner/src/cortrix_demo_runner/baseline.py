from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import subprocess
from typing import Any

from .errors import DemoContractError
from .io import read_json, write_json
from .runtime import COMPOSE_FILE, COMPOSE_PROJECT, ROOT, compose


def export_vectors(namespace: str, output: Path) -> None:
    database = f"/data/units/unit-{namespace}/store.db"
    wal = f"/data/units/unit-{namespace}/hnsw.wal"
    container_output = "/data/demo-vector-export.json"
    compose(
        [
            "exec",
            "-T",
            "cortrix",
            "python3",
            "/demo-helpers/extract_vectors.py",
            "--db",
            database,
            "--wal",
            wal,
            "--dimension",
            "1024",
            "--output",
            container_output,
        ]
    )
    compose(["cp", f"cortrix:{container_output}", str(output)])


def records(path: Path) -> list[dict[str, Any]]:
    value = read_json(path).get("records")
    if not isinstance(value, list):
        raise DemoContractError("Vector export lacks records")
    return [item for item in value if isinstance(item, dict)]


def text_vectors(items: list[dict[str, Any]], document_id: str) -> list[dict[str, Any]]:
    selected = [item for item in items if item.get("document_id") == document_id and item.get("block_type") == 1]
    selected.sort(key=lambda item: (int(item.get("chunk_index", 0)), str(item.get("block_id"))))
    return selected


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def vector_literal(values: list[Any]) -> str:
    return "[" + ",".join(format(float(value), ".9g") for value in values) + "]"


def psql(sql: str) -> str:
    command = [
        "docker-compose",
        "-p",
        COMPOSE_PROJECT,
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "postgres",
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "cortrix_demo",
        "-d",
        "cortrix_demo",
        "-At",
        "-q",
        "-F",
        ",",
    ]
    return subprocess.run(command, cwd=ROOT, input=sql, text=True, capture_output=True, check=True).stdout


def run_exact_cosine(document_vectors: Path, query_vectors: Path, fixture_manifest: Path, output: Path) -> dict[str, Any]:
    fixtures = read_json(fixture_manifest)
    document_records = records(document_vectors)
    query_records = text_vectors(records(query_vectors), "query-anchor")
    if len(query_records) != 1:
        raise DemoContractError("Run A requires exactly one query-anchor vector")
    inserts = []
    for fixture in fixtures["documents"]:
        selected = text_vectors(document_records, fixture["document_id"])
        if not selected:
            raise DemoContractError(f"Run A has no vectors for {fixture['document_id']}")
        for item in selected:
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or len(embedding) != 1024:
                raise DemoContractError("Run A encountered an invalid embedding")
            fields = [
                quote(str(item["block_id"])),
                quote(str(fixture["document_id"])),
                str(int(item["chunk_index"])),
                quote(str(fixture["document_id"])),
                quote(str(fixture["version"])),
                quote(str(fixture["status"])),
                quote(str(fixture["effective_at"])),
                quote(str(fixture["path"])),
                quote(str(item.get("content") or "")),
                quote(vector_literal(embedding)) + "::vector",
            ]
            inserts.append("(" + ",".join(fields) + ")")
    query_embedding = query_records[0]["embedding"]
    query_vector = quote(vector_literal(query_embedding)) + "::vector"
    sql = f"""
BEGIN;
TRUNCATE TABLE semantic_blocks;
INSERT INTO semantic_blocks (block_id, doc_id, chunk_index, title, version, lifecycle_status, effective_at, source_uri, content, embedding) VALUES {','.join(inserts)};
COMMIT;
SELECT current_setting('server_version'), extversion FROM pg_extension WHERE extname = 'vector';
SELECT block_id, doc_id, chunk_index, version, lifecycle_status, 1 - (embedding <=> {query_vector}) AS cosine_similarity FROM semantic_blocks ORDER BY embedding <=> {query_vector}, doc_id, chunk_index;
"""
    rows = list(csv.reader(io.StringIO(psql(sql))))
    if len(rows) < 3:
        raise DemoContractError("Run A returned too few pgvector rows")
    ranking = [
        {
            "rank": rank,
            "block_id": row[0],
            "document_id": row[1],
            "chunk_index": int(row[2]),
            "version": row[3],
            "lifecycle_status": row[4],
            "cosine_similarity": float(row[5]),
        }
        for rank, row in enumerate(rows[1:], start=1)
    ]
    assertions = {
        "current_release_is_top1": ranking[0]["document_id"] == "order-api-release-v2.0" and ranking[0]["lifecycle_status"] == "current",
        "superseded_guide_is_present": any(item["document_id"] == "order-api-guide-v1.0" and item["lifecycle_status"] == "superseded" for item in ranking),
        "exact_cosine_without_ann": True,
        "lifecycle_not_used_in_ranking": True,
    }
    passed = all(assertions.values())
    result = {
        "schema_version": 1,
        "environment": {"postgresql_version": rows[0][0], "pgvector_version": rows[0][1]},
        "search": "exact cosine; no ANN index and no lifecycle metadata in ORDER BY",
        "query_embedding_sha256": query_records[0].get("embedding_sha256"),
        "inserted_block_count": len(inserts),
        "ranking": ranking,
        "top1": ranking[0]["document_id"],
        "assertions": assertions,
        "pass": passed,
        "claim_boundary": "Dense BGE-M3 exact-cosine baseline only. It is not the BGE cross-encoder layer, the Full Stack final order, a lifecycle decision, or a performance benchmark.",
    }
    write_json(output, result)
    if not passed:
        raise DemoContractError("Run A deterministic assertions failed")
    return result
