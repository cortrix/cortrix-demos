# Run A: PostgreSQL and pgvector

Run A is the deliberately limited baseline for the Order API Field Migration scenario. It asks the same question as Run B, embeds the query and fixture chunks with BGE-M3, and ranks them in PostgreSQL/pgvector by exact cosine similarity. It does not use lifecycle metadata in ranking.

## What this path demonstrates

The query is:

> Create order now rejects a payload with account_id as an unknown field. Which request field should replace it?

The frozen synthetic corpus contains a detailed superseded v1 guide, a concise current v2 migration bulletin, and two current distractors. Because the v1 guide repeats the failing payload and error terms, the dense-only baseline places that guide first and points to the retired `account_id` field.

This is a mechanism demonstration, not a claim that PostgreSQL or pgvector cannot filter metadata. An application could add lifecycle filtering. This baseline intentionally omits it so the demo isolates the version-conflict failure mode.

## 1. Discover the scenario

From the repository root, run:

```bash
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
```

Confirm that the baseline adapter is `postgresql-pgvector`, its support status is `implemented`, and the baseline configuration is `exact cosine without lifecycle filtering`.

## 2. Validate without external calls

```bash
./democtl validate --scenario order-api-field-migration
./democtl public-safety
```

Both commands return JSON and make zero external model calls. A failure returns a structured error with `code`, `category`, `retryable`, `message`, and `structured_data`.

## 3. Inspect the frozen inputs

Read these files in order:

1. [`../fixtures/query.txt`](../fixtures/query.txt) contains the shared question.
2. [`../fixtures/manifest.json`](../fixtures/manifest.json) records fixture identity and checksums.
3. [`../profiles/technology-profile.json`](../profiles/technology-profile.json) selects the baseline adapter and frozen model identities.
4. [`../calibration/baseline-2.0.0.json`](../calibration/baseline-2.0.0.json) freezes the pre-LLM calibration that ended scenario tuning.

The calibration record is part of the anti-cherry-picking boundary: the corpus, question, and strict Run A expectation were sealed before the accepted Full Stack attempt.

## 4. Inspect the accepted Run A result

Start at [`../evidence/accepted-run.json`](../evidence/accepted-run.json), follow its `run_a` pointer, and inspect `run-a/pgvector-result.json` inside the accepted run.

The accepted result must show:

- PostgreSQL 16 and pgvector runtime identity;
- exact cosine search without an ANN index;
- no lifecycle metadata in `ORDER BY`;
- the superseded `order-api-guide-v1.0` document at rank 1;
- the current `order-api-release-v2.0` document still present in the ranking;
- all Run A assertions set to `true`.

The accepted top result is therefore the historical v1 guide and its retired field, `account_id`.

## 5. View the human projection

```bash
make viewer
```

Open the URL printed for the local viewer and select the Run A side. The viewer reads accepted evidence; it does not recompute or rewrite the result.

## 6. Understand live execution

Run A is produced as the baseline phase of the combined `run-full-stack` workflow. The repository intentionally does not expose a separate live `run-a` command because one candidate must bind Run A and Run B to the same fixtures, query, model identity, and run manifest.

Do not start a live workflow merely to inspect Run A. Use the accepted replay above. If a new candidate is explicitly authorized, follow [Run B: Cortrix Full Stack](run-b-cortrix-full-stack.md) and the repository-wide [Full Stack runbook](../../../docs/full-stack-runbook.md). The combined workflow records both paths and always applies cleanup.

## Expected conclusion

Run A answers from the most similar historical guide and recommends `account_id`. That answer is wrong for the current v2 contract. The result demonstrates the risk of a dense-only ranking contract that does not include version or lifecycle resolution; it does not establish a general database benchmark.
