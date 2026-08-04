# Run B Pipeline: Step-by-Step Runbook

This runbook explains what the runner does internally for Run B so a developer or DBA can understand the full path without reading Python source. It is explanatory: the supported live entry remains the combined `run-full-stack` command, which binds Run A and Run B into one candidate.

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

Run A and Run B share one candidate. The orchestrator completes Run A before starting Run B.

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
