# Evidence Policy

## Run states

Every run has one state:

```text
created -> running -> candidate -> accepted | rejected
```

Automation may create, run, validate, reject, or nominate a candidate. It must not mark a run accepted. Acceptance requires a human review that names the exact local commit and run ID.

Rejected runs are never screenshot-eligible. Provider or model mismatch, local generative LLM use, degraded paths, missing source identity, resolver failure, cleanup failure, secret or private-path leakage, and budget failure are rejection conditions. An accepted package is incomplete until its viewer screenshots and screenshot manifest have been verified against the same run ID and accepted code commit.

## Required identity

An accepted run records:

- scenario version and frozen assertion-contract checksum
- Cortrix release tag and release commit
- exact source revision and container digest
- fixture and model checksums
- embedding and reranker identity
- external provider, model, and non-secret base endpoint identity
- local-generative-LLM status
- Run A and Run B status
- two serial query results and durable result identity
- chunk-only query granularity and the ingestion-only role of F41 document summaries
- resolver policy and decision
- cleanup receipt
- pricing snapshot, visible usage, and estimated cost
- disclosed gaps and claim boundary

## Variable and frozen assertions

LLM wording, generated query variants, latency, and exact numeric ranking scores may vary. Provider/model identity, call count, degraded state, required retrieval paths, source identity, Run A dense top document, Run B BGE rerank leader, Run B final top document, resolver action, cleanup, secret persistence, and budget are frozen assertions.

The ranking layers are not interchangeable. Run A records dense exact cosine. Run B records the BGE cross-encoder score order and the final Full Stack response order separately. The application lifecycle policy is an independent validation layer.

## Screenshots

Screenshots are captured only from the read-only viewer rendering one accepted run. Every image records its route, run ID, source evidence path, SHA-256 digest, dimensions, and capture time. Generated illustrations and manually rewritten results are not runtime evidence.

## Candidate isolation

Candidate and rejected runs remain under ignored `.runs/`. Only sanitized accepted evidence may be copied into a scenario's tracked `evidence/runs/` directory after review.
