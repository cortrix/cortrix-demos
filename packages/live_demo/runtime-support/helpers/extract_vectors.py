#!/usr/bin/env python3
"""Extract CRC-verified float32 vectors from a Cortrix P-HNSW WAL."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
import zlib


HEADER_SIZE = 32
UINT64_MASK = (1 << 64) - 1


def parse_wal(path: Path, expected_dimension: int) -> dict[int, list[float]]:
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE or raw[:4] != b"PWAL":
        raise RuntimeError("P-HNSW WAL header is invalid")
    version, dimension = struct.unpack_from("<HI", raw, 4)
    if version != 1 or dimension != expected_dimension:
        raise RuntimeError("P-HNSW WAL version or dimension is invalid")
    if zlib.crc32(raw[:28]) & 0xFFFFFFFF != struct.unpack_from("<I", raw, 28)[0]:
        raise RuntimeError("P-HNSW WAL header checksum failed")
    vectors: dict[int, list[float]] = {}
    offset = HEADER_SIZE
    while offset < len(raw):
        entry_size = struct.unpack_from("<I", raw, offset)[0]
        frame_end = offset + 4 + entry_size
        if frame_end > len(raw):
            raise RuntimeError("P-HNSW WAL entry is truncated")
        body = raw[offset + 4 : frame_end - 4]
        if zlib.crc32(body) & 0xFFFFFFFF != struct.unpack_from("<I", raw, frame_end - 4)[0]:
            raise RuntimeError("P-HNSW WAL entry checksum failed")
        block_id = struct.unpack_from("<Q", body, 9)[0]
        if body[0] == 1:
            values = body[17:]
            if len(values) != expected_dimension * 4:
                raise RuntimeError("P-HNSW vector dimension is invalid")
            vectors[block_id] = list(struct.unpack(f"<{expected_dimension}f", values))
        elif body[0] == 2:
            vectors.pop(block_id, None)
        else:
            raise RuntimeError("P-HNSW WAL entry type is invalid")
        offset = frame_end
    return vectors


def block_context(path: Path) -> dict[int, dict]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT b.block_id, b.doc_id, b.child_id, b.chunk_index, b.block_type, b.content_text, d.metadata_json FROM blocks AS b JOIN documents AS d ON d.doc_id = b.doc_id WHERE d.deleted_at IS NULL ORDER BY b.doc_id, b.chunk_index, b.block_id"
        ).fetchall()
    finally:
        connection.close()
    result = {}
    for block_id, doc_id, child_id, chunk_index, block_type, content, metadata_json in rows:
        metadata = json.loads(metadata_json or "{}")
        unsigned = int(block_id) & UINT64_MASK
        result[unsigned] = {
            "block_id": str(unsigned),
            "child_id": child_id,
            "doc_id": doc_id,
            "document_id": metadata.get("document_id"),
            "chunk_index": chunk_index,
            "block_type": block_type,
            "content": content,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--wal", type=Path, required=True)
    parser.add_argument("--dimension", type=int, default=1024)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    vectors = parse_wal(args.wal, args.dimension)
    context = block_context(args.db)
    records = []
    for block_id, vector in sorted(vectors.items()):
        if block_id not in context:
            continue
        norm = math.sqrt(sum(value * value for value in vector))
        if not 0.999 <= norm <= 1.001:
            raise RuntimeError("Extracted vector is not L2 normalized")
        packed = struct.pack(f"<{args.dimension}f", *vector)
        records.append({**context[block_id], "embedding_dimension": args.dimension, "embedding_l2_norm": norm, "embedding_sha256": hashlib.sha256(packed).hexdigest(), "embedding": vector})
    if not records:
        raise RuntimeError("No live blocks matched P-HNSW vectors")
    result = {"schema_version": 1, "wal_sha256": hashlib.sha256(args.wal.read_bytes()).hexdigest(), "record_count": len(records), "records": records}
    args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"record_count": len(records), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
