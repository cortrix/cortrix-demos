# Layered-Ranking Contract

This scenario reports several ranking stages without treating them as interchangeable.

## Frozen layers

1. **Dense baseline:** Run A uses BGE-M3 embeddings, PostgreSQL, pgvector, and exact cosine distance. The current v2 release note must rank first. This layer does not use ANN, a cross-encoder, an LLM reranker, or lifecycle metadata.
2. **BGE cross-encoder:** Run B must expose a strictly higher BGE rerank score for the superseded v1 guide than for the current v2 release note. This is the layer described by “most similar” in the scenario title.
3. **Full Stack final order:** After DeepSeek listwise reranking, the current v2 release note must be the final top result returned by Cortrix.
4. **Application policy:** The demo application must independently select the highest final-ranked current document. In the accepted story, this preserves the current final top result rather than changing it.

## Acceptance boundary

All four layers must be present and must match the frozen document identities. A run is rejected if BGE scores are missing or tied at the top, the BGE leader is not superseded, the final top result is not current, or the application policy does not preserve that final top result.

Exact numeric scores, generated query variants, latency, and model wording may vary. Those variable values cannot replace the frozen layer identities.

Cortrix supplies the final response order, ranking scores, retrieval paths, content, and durable identity. The demo application owns lifecycle validation. The scenario demonstrates an evidence and responsibility boundary, not retrieval superiority, model superiority, or business truth from any single ranking layer.
