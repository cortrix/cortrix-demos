# Order API Field Migration

## Business question

The order creation API is failing, and the code still sends `account_id`. What should change?

Two synthetic documents are intentionally similar:

- an outdated v1.0 integration guide uses `account_id` and is marked `superseded`;
- a current v2.0 release note requires `buyer_account_id` and is marked `current`.

The reviewed scenario contract distinguishes four layers:

1. The Run A dense BGE-M3 exact-cosine baseline places the current v2 release note first.
2. The Run B BGE cross-encoder gives the superseded v1 guide the highest rerank score.
3. DeepSeek listwise reranking places the current v2 release note first in the final Full Stack response.
4. The demo application independently applies the lifecycle policy and preserves the current final top result as defense in depth.

“Most similar” in the scenario title refers only to layer 2: the highest BGE cross-encoder rerank score. It does not describe the dense baseline or final response order.

Run B uses `granularity=chunk` so each ranked result is backed by a durable text-child identity and a BGE cross-encoder score. F41 document summaries must still complete during ingestion, but they are intentionally excluded from this scenario's query candidate set.

## Responsibility boundary

Cortrix provides the final response order, BGE rerank scores, retrieved content, retrieval paths, source and document identity, and observable evidence. The demo application independently owns lifecycle validation. No single score, rank, or LLM output is business truth.

## Profiles

- `full-stack`: performs a new manual run and requires the pinned runtime, BGE models, and external `deepseek-v4-flash` access.
- `replay`: renders a previously accepted run without making external calls.

No accepted English run is included in the initial scaffold.
