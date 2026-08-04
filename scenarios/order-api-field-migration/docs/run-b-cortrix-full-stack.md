# Run B: Cortrix Full Stack

Run A and Run B are two comparison paths inside the same candidate. They share one `run_id`, question, fixture manifest, assertion contract, BGE-M3 embedding identity, source revision, and cleanup receipt. The combined workflow executes Run A first and Run B second.

Run B is the Cortrix Context Full Stack path. It adds LLM-backed ingestion, multi-path retrieval, RRF, BGE cross-encoder scoring, DeepSeek query fusion and listwise reranking, and an application lifecycle resolver.

## 1. Confirm the shared comparison contract

Both paths answer the same question:

> Create order now rejects a payload with account_id as an unknown field. Which request field should replace it?

Both paths use the same four-document synthetic corpus. The frozen comparison expects Run A to place the superseded v1 guide first and Run B to place the current v2 migration bulletin first. This is a version-conflict mechanism demo, not a performance benchmark or a general database comparison.

## 2. Choose the operating mode

| Mode | External calls | What it does |
| --- | ---: | --- |
| Accepted replay | 0 | Validates and reads the already accepted Run B evidence. Use this by default. |
| New candidate | Yes | Recreates both comparison paths under one new candidate. Requires explicit authorization. |

The guided walkthrough provides a separate live `run-b` command for human-readable observation, but it can run only after Run A in the same candidate. This preserves one fixture, query, model, source, attempt, and cleanup identity across both sides.

## 3. Discover and validate the scenario

From the repository root, run:

```bash
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
./democtl validate --scenario order-api-field-migration
./democtl verify-accepted
```

Confirm that the LLM provider adapter is `deepseek-openai-compatible`, its support status is `implemented`, the accepted run is `order-api-field-migration-20260804T085505Z`, and every command passes without an external call.

## 4. Inspect the frozen inputs

Read these files in order:

1. [`../fixtures/query.txt`](../fixtures/query.txt) contains the shared question.
2. [`../fixtures/manifest.json`](../fixtures/manifest.json) freezes the four documents, versions, lifecycle status, and checksums.
3. [`../expected/assertions.json`](../expected/assertions.json) freezes the Run A and Run B outcome contract.
4. [`../profiles/technology-profile.json`](../profiles/technology-profile.json) pins Cortrix, BGE, DeepSeek, and adapter identity for this scenario.
5. [`../calibration/baseline-2.0.0.json`](../calibration/baseline-2.0.0.json) proves that the Run A side was sealed before the accepted Full Stack attempt.

The technology profile requires Cortrix `v1.0.0-rc.1`, source revision `32b82f6f8f1d7a41349f408969ff03b7997b6c15`, `BAAI/bge-m3`, `BAAI/bge-reranker-v2-m3`, and `deepseek/deepseek-v4-flash`, with no local generative fallback.

## 5. Replay the accepted result

Start at [`../evidence/accepted-run.json`](../evidence/accepted-run.json), follow its `manifest` and `resolver` pointers, and inspect `run-b/summary.json` inside the accepted run.

For a visual replay, run:

```bash
make viewer
```

The viewer reads the same accepted evidence. It does not recompute, edit, or summarize the ranking independently.

## 6. Understand the execution path

Run B performs this pipeline:

```text
shared fixtures and query
  -> Cortrix Full Stack ingestion
  -> F03 enrichment + F35 contextualization + F38 HyPE + F41 summaries
  -> dense + lexical + contextualized + HyPE + sparse retrieval
  -> RRF fusion
  -> BGE cross-encoder scores
  -> DeepSeek listwise final order
  -> application lifecycle resolver
  -> two-query repeatability check
  -> run-b/summary.json
```

The BGE cross-encoder and DeepSeek listwise stage are intentionally observable as separate ranking layers. In the accepted run, the BGE leader remains the superseded v1 guide, while the final listwise order places the current v2 bulletin first.

Read [Run B Manual Runbook: Cortrix Full Stack](run-b-cortrix-full-stack-step-by-step.md) to reproduce the path with copy-and-paste Docker, HTTP, and Python commands. It configures and queries the underlying Cortrix service directly and does not use `democtl`.

## 7. Inspect the evidence

The accepted Run B result must show:

- four documents and five durable text blocks completed ingestion;
- F03, F35, F38, and F41 completion without recorded deterministic failures;
- dense, lexical, contextualized, HyPE, sparse, and RRF path participation;
- chunk-level durable result identity and finite BGE rerank scores;
- active, non-degraded DeepSeek query fusion and listwise reranking;
- `order-api-release-v2.0` at final response rank 1;
- an application resolver that independently preserves that current result;
- identical result order, rerank scores, and resolver decision across two serial queries.

## 8. Read the result

Run B returns the current v2 migration bulletin and therefore recommends `buyer_account_id`.

The evidence preserves three separate responsibilities: the BGE cross-encoder scores candidates, DeepSeek establishes the final response order, and the application resolver independently enforces lifecycle eligibility. No single layer is treated as business truth.

## 9. Run a new candidate only when authorized

A new candidate always executes both Run A and Run B. After completing Run A in the guided walkthrough, execute and inspect Run B, then finalize shared evidence and cleanup:

```bash
./democtl walkthrough run-b
./democtl walkthrough inspect --component run-b
./democtl walkthrough finalize
./democtl walkthrough inspect --component candidate
```

The runner restarts Cortrix with the Full Stack profile for Run B. `finalize` binds both results into the candidate manifest, removes run namespaces and containers, removes the runtime secret materialization, and records the cleanup receipt.

## 10. Stop conditions and claim boundary

A passing candidate still requires independent Clean Run acceptance before staging or screenshots.

Stop if provider, model, source, fixture, assertion, or checksum identity drifts; an ingestion feature fails; a required retrieval path is absent; an LLM stage is degraded; a durable child identity or finite BGE score is missing; the final top result is superseded; repeatability or resolver checks fail; budget is exceeded; or cleanup fails.

Run B demonstrates this accepted Full Stack contract on a synthetic corpus. It is not a universal retrieval-quality, latency, database, or cost claim. Usage visibility is partial, so the accepted run is not evidence for a public total-cost claim.

## 11. Compare with the paired run

Read [Run A: PostgreSQL and pgvector](run-a-postgresql-pgvector.md) using the same numbered sections. The comparison changes the retrieval and ranking contract while holding the question, corpus, source identity, and evidence boundary constant.
