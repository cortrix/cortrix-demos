# Layered-Ranking Contract

This scenario reports several ranking stages without treating them as interchangeable.

## Frozen layers

1. **Dense baseline:** Run A uses BGE-M3 embeddings, PostgreSQL, pgvector, and exact cosine distance. The superseded v1 guide must rank first with a strict score lead, while the current v2 bulletin remains in the observable ranking. This layer does not use ANN, a cross-encoder, an LLM reranker, or lifecycle metadata.
2. **BGE cross-encoder:** Run B records every finite BGE rerank score and its observed leader. The leader is evidence, not a frozen business assertion.
3. **Full Stack final order:** After DeepSeek listwise reranking, the current v2 release note must be the final top result returned by Cortrix.
4. **Application policy:** The demo application must independently select the highest final-ranked current document. In the accepted story, this preserves the current final top result rather than changing it.

## Acceptance boundary

All four layers must be present. A run is rejected if Run A does not strictly select the superseded v1 guide, Run B does not retrieve both version-conflict documents, BGE scores are missing, the Full Stack final top result is not the current v2 bulletin, or the application policy does not preserve that final top result.

Exact numeric scores, generated query variants, latency, and model wording may vary. Those variable values cannot replace the frozen layer identities.

Run B uses `granularity=chunk` so every result entering the BGE layer has a durable text-child identity. Document summaries must still complete during ingestion, but they are intentionally excluded from this scenario's query candidate set and are not evidence for the BGE score order.

Cortrix supplies the final response order, ranking scores, retrieval paths, content, and durable identity. The demo application owns lifecycle validation. PostgreSQL and pgvector can use metadata filters; this baseline intentionally omits them. The constructed scenario demonstrates a version-conflict mechanism and responsibility boundary, not retrieval superiority, model superiority, or business truth from any single ranking layer.
