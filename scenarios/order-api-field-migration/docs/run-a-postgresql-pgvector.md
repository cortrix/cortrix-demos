# Run A: PostgreSQL and pgvector

Run A and Run B are two comparison paths inside the same candidate. They share one `run_id`, question, fixture manifest, assertion contract, BGE-M3 embedding identity, source revision, and cleanup receipt. The combined workflow executes Run A first and Run B second.

Run A is the deliberately limited baseline. It uses BGE-M3 embeddings and PostgreSQL/pgvector exact-cosine ranking, without ANN search, lifecycle filtering, multi-path retrieval, reranking, or an LLM.

## 1. Confirm the shared comparison contract

Both paths answer the same question:

> Create order now rejects a payload with account_id as an unknown field. Which request field should replace it?

Both paths use the same four-document synthetic corpus. The frozen comparison expects Run A to place the superseded v1 guide first and Run B to place the current v2 migration bulletin first. This is a version-conflict mechanism demo, not a performance benchmark or a general database comparison.

## 2. Choose the operating mode

| Mode | External calls | What it does |
| --- | ---: | --- |
| Accepted replay | 0 | Validates and reads the already accepted Run A evidence. Use this by default. |
| New candidate | Yes, because the combined workflow also executes Run B | Recreates both comparison paths under one new candidate. Requires explicit authorization. |

The guided walkthrough provides a separate live `run-a` command for human-readable observation, but it remains inside the same candidate as Run B. This preserves one fixture, query, model, source, attempt, and cleanup identity across both sides.

## 3. Discover and validate the scenario

From the repository root, run:

```bash
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
./democtl validate --scenario order-api-field-migration
./democtl verify-accepted
```

Confirm that the baseline adapter is `postgresql-pgvector`, its support status is `implemented`, the accepted run is `order-api-field-migration-20260803T152219Z`, and every command passes without an external call.

## 4. Inspect the frozen inputs

Read these files in order:

1. [`../fixtures/query.txt`](../fixtures/query.txt) contains the shared question.
2. [`../fixtures/manifest.json`](../fixtures/manifest.json) freezes the four documents, versions, lifecycle status, and checksums.
3. [`../expected/assertions.json`](../expected/assertions.json) freezes the Run A and Run B outcome contract.
4. [`../profiles/technology-profile.json`](../profiles/technology-profile.json) selects the baseline and Full Stack technologies for this scenario.
5. [`../calibration/baseline-2.0.0.json`](../calibration/baseline-2.0.0.json) records the sealed Run A ranking created before the accepted LLM-backed attempt.

The calibration record is the anti-cherry-picking boundary: the corpus, query, and strict Run A expectation were frozen before the accepted Full Stack execution.

## 5. Replay the accepted result

Start at [`../evidence/accepted-run.json`](../evidence/accepted-run.json), follow its `run_a` pointer, and inspect `run-a/pgvector-result.json` inside the accepted run.

For a visual replay, run:

```bash
make viewer
```

The viewer reads the same accepted evidence. It does not recompute, edit, or summarize the ranking independently.

## 6. Understand the execution path

Run A performs this pipeline:

```text
shared fixtures and query
  -> Cortrix embedding-only runtime
  -> BGE-M3 document and query vectors
  -> vector export
  -> PostgreSQL semantic_blocks table
  -> pgvector exact-cosine ORDER BY
  -> deterministic Run A assertions
  -> run-a/pgvector-result.json
```

The embedding-only Cortrix runtime is used only to produce the same pinned BGE-M3 embeddings used by the comparison. It does not execute Cortrix Full Stack retrieval, RRF, reranking, lifecycle resolution, or any LLM call for Run A.

Read [Run A Manual Runbook: PostgreSQL and pgvector](run-a-postgresql-pgvector-step-by-step.md) to reproduce the path with copy-and-paste Docker, HTTP, Python, and SQL commands. It operates the underlying services directly and does not use `democtl`.

## 7. Inspect the evidence

The accepted Run A result must show:

- PostgreSQL and pgvector runtime versions;
- one 1024-dimensional query-anchor embedding;
- five durable document text-block embeddings inserted into `semantic_blocks`;
- exact cosine distance using pgvector's `<=>` operator;
- no ANN index and no lifecycle field in `ORDER BY`;
- the superseded `order-api-guide-v1.0` at rank 1;
- the current `order-api-release-v2.0` still present in the ranking;
- every Run A assertion set to `true`.

## 8. Read the result

Run A returns the historical v1 guide as the nearest dense result and therefore exposes the retired `account_id` field. That answer is wrong for the current v2 contract.

The result demonstrates a specific failure mode: semantic similarity alone can favor a detailed outdated guide when version or lifecycle policy is outside the ranking contract.

## 9. Run a new candidate only when authorized

A new candidate always executes both Run A and Run B. Follow the repository-wide [Full Stack runbook](../../../docs/full-stack-runbook.md), initialize one walkthrough, and execute Run A first:

```bash
./democtl walkthrough init --reviewed-attempt-limit 2
./democtl walkthrough run-a
./democtl walkthrough inspect --component run-a
```

Continue with the paired Run B Runbook. Do not start another walkthrough between the two paths. Both results are bound into the same candidate manifest and cleanup receipt.

## 10. Stop conditions and claim boundary

A passing candidate still requires independent Clean Run acceptance before staging or screenshots.

Stop if fixture or assertion checksums drift, the query anchor is missing or duplicated, an embedding is not 1024-dimensional, PostgreSQL/pgvector fails, fewer than the expected rows are returned, the frozen v1 top result is not strict, the current v2 document disappears from the ranking, or cleanup fails.

PostgreSQL and pgvector can apply metadata filters and more advanced retrieval designs. This profile intentionally does not. Run A is not a claim about the maximum capability of PostgreSQL or pgvector.

## 11. Compare with the paired run

Read [Run B: Cortrix Full Stack](run-b-cortrix-full-stack.md) using the same numbered sections. The comparison changes the retrieval and ranking contract while holding the question, corpus, source identity, and evidence boundary constant.
