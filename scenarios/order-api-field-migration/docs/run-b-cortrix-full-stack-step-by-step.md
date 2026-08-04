# Run B Pipeline: Step-by-Step Runbook

This runbook lets a developer or DBA continue the same candidate into Run B, execute it command by command, and understand every internal operation without reading Python source. Complete the paired Run A Runbook first; Run B cannot initialize a separate comparison candidate.

The output excerpts below come from real candidate `order-api-field-migration-20260804T085505Z`. A later run receives a different `run_id`, but the frozen document identities, retrieval-path contract, ranking layers, resolver decision, and assertions must match.

## Walkthrough step 1 — Validate the shared workspace

Return to the same repository checkout used for Run A and inspect the active session:

```bash
./democtl walkthrough status
```

The output must identify the same `run_id` and must show:

```json
{
  "status": "run_a_complete",
  "next_command": "./democtl walkthrough run-b"
}
```

Do not edit tracked files, switch commits, or initialize a second walkthrough between the two paths. The runner fails closed if checkout identity changes.

## Walkthrough step 2 — Confirm the shared comparison

Print the exact question again:

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/order-api-field-migration/fixtures/query.txt").read_text().strip())'
```

Expected output:

```text
Create order now rejects a payload with account_id as an unknown field. Which request field should replace it?
```

Inspect Run A before continuing:

```bash
./democtl walkthrough inspect --component run-a
```

Confirm that `order-api-guide-v1.0` is the superseded rank-1 result and `pass` is `true`. Run B must answer the same question over the same frozen corpus.

## Walkthrough step 3 — Prepare the shared candidate

Restore the key if this is a new shell. Confirm only its presence:

```bash
test -n "${DEEPSEEK_API_KEY:-}" && echo "DEEPSEEK_API_KEY is set"
```

Check that Docker is reachable and that the walkthrough remains at the required phase:

```bash
docker info >/dev/null
docker-compose version
./democtl walkthrough status
```

Run B performs the authorized external DeepSeek calls. It must use `deepseek/deepseek-v4-flash`; local generative fallback, provider substitution, degraded stages, or missing usage identity rejects the candidate.

## Walkthrough step 4 — Execute this path

Continue the current candidate:

```bash
./democtl walkthrough run-b
```

Docker Compose may print local service lifecycle lines before the JSON summary. The stable result is the final JSON object. The real reference run reported:

```json
{
  "status": "pass",
  "run_id": "order-api-field-migration-20260804T085505Z",
  "phase": "run_b_complete",
  "runtime_profile": "full-stack",
  "provider": "deepseek",
  "model": "deepseek-v4-flash",
  "retrieval_paths": {
    "contextualized": 4,
    "dense": 4,
    "fts5": 4,
    "hype_question": 4,
    "sparse": 4
  },
  "bge_leader": {
    "document_id": "order-api-guide-v1.0",
    "version": "v1.0",
    "lifecycle_status": "superseded",
    "bge_rerank_rank": 1
  },
  "final_top_result": {
    "document_id": "order-api-release-v2.0",
    "version": "v2.0",
    "lifecycle_status": "current",
    "final_response_rank": 1
  },
  "cleanup_required": true
}
```

Run `finalize` after inspection even when the result passes; until finalization, runtime cleanup and candidate evidence are incomplete.

## Walkthrough step 5 — Inspect the real result

Read the sanitized evidence projection:

```bash
./democtl walkthrough inspect --component run-b
```

Verify these key fields:

```json
{
  "ingestion_completion": {
    "expected_document_count": 4,
    "expected_text_block_count": 5,
    "expected_hype_question_count": 15,
    "pass": true
  },
  "layers": {
    "bge_cross_encoder": {
      "leader": {
        "document_id": "order-api-guide-v1.0",
        "lifecycle_status": "superseded",
        "bge_rerank_score": 0.9467289447784424
      }
    },
    "deepseek_listwise_final": {
      "top_result": {
        "document_id": "order-api-release-v2.0",
        "lifecycle_status": "current",
        "bge_rerank_score": 0.6197220683097839
      }
    },
    "application_lifecycle_policy": {
      "action": "preserved_final_top1"
    }
  },
  "decision": {
    "selected_document_id": "order-api-release-v2.0",
    "selected_version": "v2.0",
    "selected_field": "buyer_account_id"
  },
  "repeat": {
    "result_order_identical": true,
    "rerank_scores_identical": true,
    "resolver_decision_identical": true,
    "pass": true
  },
  "pass": true
}
```

The complete output also shows every ingestion and retrieval-path assertion. All must be `true`.

## Walkthrough step 6 — Interpret the real result

Run B preserves the layered-ranking story instead of hiding it. BGE cross-encoder similarity alone still prefers the old v1 guide. Cortrix Full Stack then uses the configured multi-path retrieval, RRF, DeepSeek query fusion, and DeepSeek listwise ordering to place the current v2 release bulletin first. The application lifecycle resolver independently confirms that the final top result is eligible and selects `buyer_account_id`.

This result shows why the Full Stack contract succeeds in this constructed version-conflict scenario. It is not a universal retrieval-quality, database, latency, or cost claim.

## Walkthrough step 7 — Continue or close the candidate

Finalize immediately after Run B:

```bash
./democtl walkthrough finalize
./democtl walkthrough inspect --component candidate
```

The real reference candidate reported:

```json
{
  "run_id": "order-api-field-migration-20260804T085505Z",
  "state": "candidate",
  "assertions": {
    "run_a": true,
    "run_b": true,
    "required_paths": true,
    "resolver": true,
    "cleanup": true,
    "budget": true,
    "model_checksums": true,
    "all_passed": true
  },
  "cleanup": {
    "namespaces_removed": true,
    "containers_removed": true,
    "ports_released": true,
    "runtime_secret_removed": true
  },
  "cost": {
    "budget_usd": 1.0,
    "observable_input_tokens": 549,
    "observable_output_tokens": 181,
    "observable_call_count_minimum": 5,
    "estimated_observable_cost_usd": 0.00012754,
    "estimated_total_usd": null,
    "usage_visibility": "partial",
    "public_cost_claim_allowed": false,
    "within_budget_contract": true
  },
  "human_review_required": true
}
```

Partial usage visibility means this evidence cannot support a public total-cost claim. A passing candidate still requires independent Clean Run acceptance before evidence staging or screenshots.

## Walkthrough step 8 — Recover safely

If Run B finishes but your shell closes before cleanup, return to the same clean checkout and run:

```bash
./democtl walkthrough status
```

When the phase is `run_b_complete`, run `./democtl walkthrough finalize`. When the phase is already `candidate`, inspect it with `./democtl walkthrough inspect --component candidate`; do not execute Run B again.

If an active walkthrough cannot continue, reject and clean it up:

```bash
./democtl walkthrough abort
```

Never rerun a deterministic failure, create screenshots from a candidate, or stage rejected evidence.

## Pipeline at a glance

```text
frozen inputs
  -> common preflight and candidate reservation
  -> Cortrix Full Stack runtime
  -> document ingestion and durable identity
  -> LLM-backed enrichment and derived indexes
  -> multi-path retrieval
  -> RRF and BGE cross-encoder scoring
  -> DeepSeek listwise final order
  -> application lifecycle resolver
  -> evidence and shared cleanup
```

Run A and Run B share one candidate. The orchestrator completes Run A before starting Run B. The walkthrough output is intentionally more verbose than a production application response because it is an educational and audit surface.

## Stage 0 — Freeze shared inputs

The runner loads the scenario contract, fixture manifest, query, retrieval contract, and frozen assertions. It verifies every fixture checksum before runtime work and verifies that the demo checkout is clean, on `main`, and attributable to a full commit.

Run B consumes the same four fixture documents and the same query as Run A. The technology profile pins Cortrix release and source revision, BGE-M3, the BGE reranker, DeepSeek provider/model/roles, the required secret name, and the no-local-fallback rule.

Evidence: `fixtures/manifest.json`, `expected/assertions.json`, `profiles/technology-profile.json`, and the candidate `source-manifest.json`.

## Stage 1 — Pass preflight and reserve the candidate

The runner requires `DEEPSEEK_API_KEY` in the process environment but never records its value. It verifies the pinned Cortrix source revision and release ancestry, Docker and Docker Compose availability, the current official pricing snapshot, the reviewed attempt limit, and the conservative cumulative budget bound.

It then verifies fixture checksums and the clean demo checkout before reserving a campaign slot. The attempt ledger records the `run_id`, scenario version, demo commit, and reserved state.

Evidence: `.runs/campaigns/<campaign_id>.json`, `state-history.json`, and `preflight.json` in a local candidate.

## Stage 2 — Start the runtime

Before Run A starts, the runner verifies or builds the pinned Cortrix container image and checks its source-revision label. After Run A completes, it restarts Cortrix with the Full Stack profile and materializes a mode-`0600` runtime config by replacing three tracked placeholders with the environment-injected key.

Docker Compose starts PostgreSQL and force-recreates Cortrix in `full-stack` mode. The runner polls `/api/v1/system/health/ready`, verifies BGE-M3 and BGE reranker file checksums inside the container, and sends one direct DeepSeek contract smoke requiring the exact `deepseek-v4-flash` model identity.

The smoke response content is not persisted. Only provider, model, call count, and observable usage are recorded.

## Stage 3 — Prepare data for this path

The runner derives one Run B namespace, `order-b-<suffix>`, from the shared `run_id`. It captures metrics before ingestion, creates the namespace if necessary, and uploads the four fixture documents with frozen metadata, run ID, and fixture checksum.

Each `POST /documents` returns an asynchronous task ID. The runner polls each task's progress endpoint until success, rejects any successful-looking task that still reports an error field, and stops on failed, cancelled, or timed-out tasks.

After ingestion, the runner inspects the durable namespace store and builds a `child_id -> document_id -> fixture document_id` identity map. The resolver later uses this map instead of trusting a presentation-only source field.

## Stage 4 — Produce retrieval inputs

The Full Stack enrichment gate waits until the actual durable block count satisfies every required feature:

- F03 has enriched every text block;
- F35 has generated contextualized text for every text block;
- F38 has generated three HyPE questions per text block;
- F41 has generated one document summary per fixture document;
- every text block has a successful final enrichment state.

The accepted corpus produces five durable text blocks, fifteen HyPE questions, and four document summaries. Metrics and durable inspection must agree. Any recorded F35, F38, or F41 failure is deterministic and immediately rejects the candidate.

F41 summaries are required ingestion evidence but are excluded from this scenario's chunk-level query candidate set.

## Stage 5 — Execute retrieval

The runner reads the same frozen query used by Run A and submits it twice, serially, with:

- `top_k=4` and `granularity=chunk`;
- the `complex` route;
- vector and BM25/FTS retrieval enabled;
- query explain output enabled;
- RAG fusion always active with three generated variants;
- candidate multiplier 5 and maximum 20 candidates;
- BGE reranking enabled;
- DeepSeek listwise reranking enabled for the top four candidates.

Each query captures metrics before and after the request. Raw request, response, and metrics are persisted in the ignored candidate directory before resolver assertions run, so a later failure cannot erase the observed response.

## Stage 6 — Apply ranking

Run B keeps the ranking layers separate:

1. Dense, lexical, contextualized, HyPE-question, and sparse paths produce candidate lists.
2. RRF combines those path rankings.
3. The BGE cross-encoder assigns a `rerank_score` to each durable chunk candidate.
4. DeepSeek listwise reranking establishes the final response order.

The runner verifies path participation through `explain.rrf_path_counts`, RAG fusion status, listwise status, model identity, and metric deltas. It rejects degraded LLM stages or missing BGE activity.

In the accepted run, the BGE cross-encoder's highest score belongs to the superseded v1 guide, but DeepSeek listwise reranking places the current v2 bulletin at final rank 1. Both observations remain visible.

## Stage 7 — Resolve result

The demo application applies an independent lifecycle resolver to the final Cortrix response. It maps each durable child ID back to the frozen fixture identity, marks current documents as eligible, and selects the highest final-ranked current document.

The resolver does not rewrite Cortrix scores or reorder the evidence. In the accepted run, it preserves the existing final top result, `order-api-release-v2.0`, and selects `buyer_account_id`.

The runner then verifies that the required v1/v2 conflict documents were retrieved, BGE scores are finite, the final top result is current, and every layered assertion passes.

## Stage 8 — Persist evidence

For each of the two serial queries, the runner writes request, response, before/after metrics, and resolver output. It writes durable inspection, identity map, ingestion summary, repeatability summary, model checksums, provider smoke, preflight, runtime identity, source manifest, cost record, and final run manifest.

Observable query-fusion and smoke usage is counted, but internal ingestion and listwise calls do not expose complete usage. The manifest therefore records `usage_visibility=partial`, leaves total estimated cost unset, and prohibits a public total-cost claim.

## Stage 9 — Clean up

Cleanup removes the Run B namespace and the two paired Run A namespaces derived from the same `run_id`, stops the dedicated Compose project, deletes the runtime config that contained the injected key, and verifies that ports `18420`, `19091`, and `15432` no longer have listeners.

Model caches and Docker volumes are intentionally preserved. The cleanup receipt must confirm namespace removal, container removal, port release, and runtime-secret removal.

## Stage 10 — Verify acceptance conditions

Run B passes only when ingestion completion, required retrieval paths, chunk identity, BGE activity, non-degraded DeepSeek stages, application resolver, and two-query repeatability all pass.

The whole candidate also requires Run A, cleanup, budget, and model-checksum assertions. A candidate is not accepted evidence and is not screenshot-eligible. Independent Clean Run acceptance is required before staging, and the accepted pointer, run manifest, resolver, screenshots, and checksums must remain one identity chain.

## Evidence map

| Question | Evidence |
| --- | --- |
| Which source, fixtures, and models were used? | `source-manifest.json`, `fixture-manifest.json`, and `model-checksums.json` |
| Did every ingestion feature complete? | `run-b/summary.json`, durable inspection, and before/after ingestion metrics |
| Which retrieval paths participated? | `query_attempts[].rrf_path_counts` and query metrics |
| What did BGE score versus the final listwise order? | `resolver.layers.bge_cross_encoder` and `resolver.layers.deepseek_listwise_final` |
| Why was the v2 document selected? | `run-b/resolver-01.json` and `resolver.decision` in the summary |
| Were results repeatable? | `repeat` in `run-b/summary.json` |
| Did cleanup finish? | `cleanup-receipt.json` referenced by the run manifest |

## Operational boundaries

- Do not execute the internal stages manually and present them as an official candidate; use the combined runner.
- Do not accept a provider/model substitution, degraded LLM stage, local generative fallback, missing retrieval path, or unresolved durable identity.
- Do not treat the BGE score, DeepSeek order, or lifecycle resolver alone as business truth.
- Do not publish a total-cost, latency, or general retrieval-superiority claim from this mechanism demo.
