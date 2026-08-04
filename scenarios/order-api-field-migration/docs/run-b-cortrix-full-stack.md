# Run B: Cortrix Full Stack

Run B uses the same question and frozen corpus as Run A, but executes the Cortrix Context Full Stack. It preserves evidence for ingestion enrichment, multi-path retrieval, fusion, cross-encoder scores, DeepSeek query expansion and listwise reranking, and the application lifecycle resolver.

## What this path demonstrates

The shared query is:

> Create order now rejects a payload with account_id as an unknown field. Which request field should replace it?

The accepted final response places the current v2 migration bulletin first and returns `buyer_account_id`. The BGE cross-encoder alone still gives its highest score to the superseded v1 guide. DeepSeek listwise reranking changes the final order, and the demo application independently verifies that the selected document is current.

This layered result is the scenario contract. No single retrieval score, ranking layer, or LLM output is treated as business truth.

## 1. Replay the accepted result first

From the repository root, run the safe path:

```bash
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
./democtl validate --scenario order-api-field-migration
./democtl verify-accepted
```

These commands make zero external model calls. Confirm that the accepted run ID is `order-api-field-migration-20260803T152219Z` and that accepted verification passes.

## 2. Inspect the technology contract

Read [`../profiles/technology-profile.json`](../profiles/technology-profile.json). The implemented Run B profile pins:

- Cortrix release `v1.0.0-rc.1`;
- source revision `32b82f6f8f1d7a41349f408969ff03b7997b6c15`;
- embedding model `BAAI/bge-m3`;
- reranker model `BAAI/bge-reranker-v2-m3`;
- provider/model `deepseek/deepseek-v4-flash`;
- `DEEPSEEK_API_KEY` as the only accepted secret environment variable;
- no local generative fallback.

The profile also declares the required capabilities. A missing or unsupported adapter fails before external work.

## 3. Inspect the accepted layers

Start at [`../evidence/accepted-run.json`](../evidence/accepted-run.json), follow its `manifest` and `resolver` pointers, and inspect `run-b/summary.json` inside the accepted run.

The accepted evidence must show:

1. All four documents and five durable text blocks completed ingestion.
2. F03 enrichment, F35 contextualization, HyPE questions, and F41 document summaries completed without recorded failures.
3. Both serial queries used dense, lexical, contextualized, HyPE, sparse, and RRF paths.
4. Each candidate has a durable chunk identity and a finite BGE cross-encoder score.
5. DeepSeek query fusion and listwise reranking were active and non-degraded.
6. The final Full Stack order placed `order-api-release-v2.0` first.
7. The application resolver selected the current v2 document and preserved that final top result.
8. Repeated queries produced identical final order, scores, and resolver decision.

The expected current field is `buyer_account_id`.

## 4. View the accepted evidence

```bash
make viewer
```

Open the URL printed for the local viewer. The Run B panel, technology profile, execution path, evidence identity, and screenshot all resolve from the accepted run. The viewer fails closed if those identities disagree.

## 5. Prepare a live candidate only when authorized

A live run is manual, cost-bearing, and unnecessary for replay. Before running it:

1. Place the pinned Cortrix checkout at `.runtime/cortrix-src`.
2. Record current official provider pricing in `.runs/pricing-snapshot.json` as described in the [Full Stack runbook](../../../docs/full-stack-runbook.md).
3. Inject `DEEPSEEK_API_KEY` through the process environment. Never put its value in a file or command argument.
4. Confirm that the explicit authorization covers a new attempt and that the conservative bound remains within the repository-wide `USD 1.00` ceiling.
5. Run the fail-closed preflight:

```bash
./democtl preflight --scenario order-api-field-migration --profile full-stack
```

Only after preflight passes and the action remains authorized, run:

```bash
./democtl run-full-stack --scenario order-api-field-migration
```

The combined workflow produces both Run A and Run B for one candidate. It allows no local generative fallback, does not print the secret, and does not promote its own result.

## 6. Inspect and clean up the candidate

Candidate evidence is written under ignored `.runs/<run_id>/`. Inspect the candidate manifest, Run A ranking, both serialized Run B queries, resolver outputs, model checksums, pricing snapshot, usage visibility, runtime identity, and cleanup receipt.

The workflow cleans only resources derived from its run ID and preserves shared model caches and Docker volumes. A rejected candidate remains rejected. A passing candidate still requires independent Clean Run acceptance before it can be staged under tracked accepted evidence or used for a screenshot.

## Stop conditions

Stop and reject the candidate if provider or model identity drifts, a required retrieval path is absent, an LLM path is degraded, the resolver fails, the source revision or model checksum changes, cleanup is incomplete, a secret or private path leaks, or the budget gate fails. Deterministic assertion failures must not be automatically rerun.

## Expected conclusion

Run B returns the current v2 migration bulletin and recommends `buyer_account_id`. The evidence also shows why the outcome is layered: BGE cross-encoder scoring, DeepSeek final ordering, and application lifecycle validation remain separate, observable responsibilities.
