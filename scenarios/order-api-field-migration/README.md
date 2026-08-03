# Order API Field Migration

## Business question

Create Order rejects a payload with `account_id` as an unknown field. Which request field should replace it?

This synthetic scenario is constructed to isolate a common API version-conflict failure mode. It contains four same-domain documents:

- a detailed historical v1.0 integration guide that repeats the failing payload and `account_id` error terms;
- a concise current v2.0 migration bulletin that requires `buyer_account_id`;
- two current Order API distractors covering pagination and cancellation.

The reviewed scenario contract distinguishes four layers:

1. The Run A BGE-M3 dense-only exact-cosine baseline, intentionally configured without lifecycle filtering, must place the superseded v1 guide first.
2. Run B must retrieve both version-conflict documents through a non-degraded Cortrix Context Full Stack query.
3. DeepSeek listwise reranking must place the current v2 migration bulletin first in the final Full Stack response.
4. The demo application independently applies the lifecycle policy and preserves the current v2 result as defense in depth.

The BGE cross-encoder leader and score are observable evidence, but they are not a frozen business outcome. The frozen comparison is Run A v1 versus Run B v2.

The [sealed local calibration record](calibration/baseline-2.0.0.json) contains the exact input checksums and Run A ranking used to end scenario tuning before any DeepSeek call.

Run B uses `granularity=chunk` so each ranked result is backed by a durable text-child identity and a BGE cross-encoder score. F41 document summaries must still complete during ingestion, but they are intentionally excluded from this scenario's query candidate set.

## Responsibility boundary

Cortrix provides the final response order, BGE rerank scores, retrieved content, retrieval paths, source and document identity, and observable evidence. The demo application independently owns lifecycle validation. No single score, rank, or LLM output is business truth.

## Profiles

- `full-stack`: performs a new manual run and requires the pinned runtime, BGE models, and external `deepseek-v4-flash` access.
- `replay`: renders a previously accepted run without making external calls.

The previous 1.2.0 accepted evidence is retained as historical evidence. It does not satisfy the current 2.0.0 contract and is not replayed by the current accepted-run pointer.
