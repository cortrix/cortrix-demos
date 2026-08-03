CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS semantic_blocks (
    block_id text PRIMARY KEY,
    doc_id text NOT NULL,
    chunk_index integer NOT NULL,
    title text NOT NULL,
    version text NOT NULL,
    lifecycle_status text NOT NULL,
    effective_at date NOT NULL,
    source_uri text NOT NULL,
    content text NOT NULL,
    embedding vector(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS semantic_blocks_document_idx ON semantic_blocks (doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS semantic_blocks_lifecycle_idx ON semantic_blocks (lifecycle_status, effective_at DESC);
