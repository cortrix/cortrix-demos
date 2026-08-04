# Run A Pipeline: Step-by-Step Runbook

This runbook explains what the runner does internally for Run A so a developer or DBA can understand the full path without reading Python source. It is explanatory: the supported live entry remains the combined `run-full-stack` command, which binds Run A and Run B into one candidate.

## Pipeline at a glance

```text
frozen inputs
  -> common preflight and candidate reservation
  -> embedding-only Cortrix runtime
  -> two isolated namespaces
  -> BGE-M3 vector generation
  -> vector export
  -> PostgreSQL/pgvector load
  -> exact-cosine query
  -> deterministic assertions
  -> evidence and shared cleanup
```

Run A and Run B share one candidate. The orchestrator completes Run A before starting Run B.

## Stage 0 — Freeze shared inputs

The runner loads the scenario contract, fixture manifest, query, and frozen assertions. It verifies every fixture checksum before runtime work and verifies that the demo checkout is clean, on `main`, and attributable to a full commit.

Run A consumes the same four fixture documents and the same query as Run B. The fixture metadata includes `document_id`, version, lifecycle status, effective date, and source path. The frozen assertion contract names the expected Run A top document and requires the current v2 document to remain observable in the ranking.

Evidence: `fixtures/manifest.json`, `expected/assertions.json`, `calibration/baseline-2.0.0.json`, and the candidate `source-manifest.json`.

## Stage 1 — Pass preflight and reserve the candidate

The combined workflow validates source identity, Docker, Docker Compose, pricing, secret presence, attempt limit, and the USD budget before reserving a campaign slot. Although Run A itself makes no external LLM call, it shares this preflight because its evidence must be paired with Run B under one candidate.

The attempt ledger records the `run_id`, scenario version, demo commit, and reserved state before runtime work begins. A deterministic failure consumes the reserved slot and cannot silently become accepted evidence.

Evidence: `.runs/campaigns/<campaign_id>.json`, `state-history.json`, and `preflight.json` in a local candidate.

## Stage 2 — Start the runtime

The runner starts with the embedding-only profile. It materializes a local runtime config with `CORTRIX_LLM_ENABLED=false`, starts the PostgreSQL service, and force-recreates the Cortrix service.

The Cortrix service uses pinned BGE-M3 assets with 1024-dimensional embeddings. The PostgreSQL service uses the pgvector PostgreSQL 16 image and initializes the `semantic_blocks` table. All listeners bind to loopback addresses.

No DeepSeek request, query fusion, contextual enrichment, HyPE generation, document summary, listwise rerank, or local generative fallback is part of Run A.

Evidence: `runtime/config/cortrix.embedding-only.yaml`, `runtime/docker-compose.yml`, and the candidate runtime identity.

## Stage 3 — Prepare data for this path

The runner derives two namespace names from the shared `run_id`:

- `order-a-docs-<suffix>` stores the four fixture documents;
- `order-a-query-<suffix>` stores a single `query-anchor.txt` document.

Each fixture is uploaded with its frozen metadata and checksum. The runner waits for each asynchronous document task to report a successful terminal state. The query text is uploaded separately with `document_id=query-anchor` and `role=query_embedding_anchor` so its vector cannot be confused with a corpus block.

Evidence: document task responses in local candidate processing and the cleanup receipt's namespace list.

## Stage 4 — Produce retrieval inputs

Cortrix's embedding-only runtime chunks the fixture documents and applies the pinned BGE-M3 model. The accepted corpus produces five durable text blocks from four documents. It also embeds the single query anchor.

The runner exports vectors from each namespace's durable Cortrix store and WAL using the repository helper. It selects only text blocks, orders them by chunk index and block ID, and requires exactly one query-anchor vector.

Every selected embedding must contain 1024 numeric dimensions. The query vector checksum is carried into Run A evidence.

Evidence in a local candidate: `run-a/document-vectors.json` and `run-a/query-vectors.json`. These raw exports are not part of the curated accepted public evidence; the sanitized ranking result is.

## Stage 5 — Execute retrieval

The runner converts every vector to a pgvector literal and creates one SQL transaction:

1. `TRUNCATE semantic_blocks` removes data from a prior local attempt inside the dedicated demo database.
2. `INSERT` writes block identity, document identity, chunk index, title, version, lifecycle status, effective date, source URI, content, and embedding.
3. A version query records PostgreSQL and pgvector versions.
4. A `SELECT` computes `1 - (embedding <=> query_vector)` as cosine similarity.
5. `ORDER BY embedding <=> query_vector, doc_id, chunk_index` establishes deterministic dense order and tie-breaking.

There is no ANN index. `version`, `lifecycle_status`, and `effective_at` are stored for observation but are not used in `WHERE` or `ORDER BY`.

## Stage 6 — Apply ranking

pgvector exact cosine is the only retrieval and ranking signal. The runner enumerates every returned block and records rank, block ID, document ID, chunk index, version, lifecycle status, and cosine similarity.

There is no BM25, contextualized recall, HyPE recall, sparse recall, RRF fusion, BGE cross-encoder reranking, DeepSeek listwise reranking, or lifecycle boost in Run A.

In the accepted result, the detailed v1 guide receives the highest cosine similarity because it repeats the failing payload and error wording.

## Stage 7 — Resolve result

Run A has no application lifecycle resolver. Its output is intentionally the raw dense top result.

Instead, deterministic assertions verify that:

- the frozen superseded v1 document is top 1;
- its similarity is strictly greater than rank 2;
- the current v2 migration bulletin is still present;
- exact cosine and no-lifecycle-ranking boundaries are declared.

This is the core contrast: Run A exposes what the chosen dense-only contract returns before any business lifecycle policy is applied.

## Stage 8 — Persist evidence

The runner writes `run-a/pgvector-result.json`. The candidate run manifest references that file and records its pass state alongside the paired Run B result, shared source identity, provider identity, model checksums, cleanup receipt, budget record, and claim boundary.

The curated accepted Run A evidence retains the ranking result but not local runtime paths, raw secrets, or ignored transient files.

## Stage 9 — Clean up

Cleanup removes the two Run A namespaces and the paired Run B namespace derived from the same `run_id`, stops the dedicated Compose project, deletes the runtime config that could contain the injected Run B secret, and verifies that ports `18420`, `19091`, and `15432` no longer have listeners.

Model caches and Docker volumes are intentionally preserved. The cleanup receipt must confirm namespace removal, container removal, port release, and runtime-secret removal.

## Stage 10 — Verify acceptance conditions

Run A passes only when its deterministic assertions pass. The whole candidate still requires Run B, required-path, resolver, cleanup, budget, and model-checksum assertions to pass before it can reach `candidate` state.

A candidate is not accepted evidence and is not screenshot-eligible. Independent Clean Run acceptance is required before staging. The accepted pointer, run manifest, Run A result, resolver, screenshot manifest, and checksums must remain one identity chain.

## Evidence map

| Question | Evidence |
| --- | --- |
| Which inputs were used? | `fixtures/manifest.json` and candidate `source-manifest.json` |
| Which query vector was used? | `query_embedding_sha256` in `run-a/pgvector-result.json` |
| Which database versions ran? | `environment` in `run-a/pgvector-result.json` |
| Was lifecycle used for ranking? | `search`, SQL contract, and `lifecycle_not_used_in_ranking` assertion |
| What was the complete dense order? | `ranking[]` in `run-a/pgvector-result.json` |
| Did cleanup finish? | `cleanup-receipt.json` referenced by the run manifest |

## Operational boundaries

- Do not execute the internal stages manually and present them as an official candidate; use the combined runner.
- Do not add lifecycle filtering to Run A without creating a new scenario/profile contract and recalibrating before any LLM-backed attempt.
- Do not describe this baseline as the maximum capability of PostgreSQL or pgvector.
- Do not compare latency or cost from this mechanism demo.
