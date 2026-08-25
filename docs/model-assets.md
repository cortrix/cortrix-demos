# Model Asset Preparation

Live execution requires four local model assets in the Cortrix data volume. Accepted replay does not require them.

| Component | Declared model | Required SHA-256 |
| --- | --- | --- |
| Embedding model | `BAAI/bge-m3` | `2237f770aad5c71bbc1fc2d361a57f9a37400574cc9eff32626f0cdb49234730` |
| Embedding tokenizer | `BAAI/bge-m3` | `249df0778f236f6ece390de0de746838ef25b9d6954b68c2ee71249e0a9d8fd4` |
| Reranker model | `BAAI/bge-reranker-v2-m3` | `912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d` |
| Reranker tokenizer | `BAAI/bge-reranker-v2-m3` | `8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3` |

The current accepted package records these checksums but does not contain a public, checksum-reproducible export recipe for the exact Cortrix-compatible ONNX files. Files currently published on upstream model branches must not be downloaded and renamed unless their bytes match the required checksums.

This is a live-reproduction blocker, not a reason to weaken the checksum gate. Before a new public live campaign, the project must publish one of the following:

1. a source revision and deterministic export recipe that produces the exact files;
2. a separately licensed release artifact with source, license, SHA-256, and provenance; or
3. a newly reviewed model identity followed by a new candidate and Clean Room.

The BGE-M3 model card currently declares MIT, while the BGE reranker model card currently declares Apache-2.0. Review the exact upstream revisions and licenses again before distributing any model artifact. This repository does not redistribute model weights.
