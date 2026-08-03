# Full Stack runbook

This is a manual, cost-bearing workflow. The runner fails closed and does not use a local generative LLM.

## 1. Supply the pinned Cortrix source

Place a source checkout at `.runtime/cortrix-src` and verify that its `HEAD` is exactly `32b82f6f8f1d7a41349f408969ff03b7997b6c15`. The runner also verifies that release commit `e159974f936bd987d5718195d54cd70ff3acc2e5` is an ancestor of that source revision.

The source checkout is ignored. Its local path is never written to curated evidence.

## 2. Record current official pricing

Immediately before a live run, read the official [DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing) and create `.runs/pricing-snapshot.json` with this shape:

```json
{
  "schema_version": 1,
  "observed_at": "RFC-3339 timestamp",
  "official_url": "https://api-docs.deepseek.com/quick_start/pricing",
  "provider": "deepseek",
  "model": "deepseek-v4-flash",
  "currency": "USD",
  "unit": "per_million_tokens",
  "prices_per_million_tokens": {
    "input_cache_hit": 0.0,
    "input_cache_miss": 0.0,
    "output": 0.0
  },
  "notes": "Replace zero placeholders with the prices observed on the official page."
}
```

The runner computes a conservative two-attempt cost bound from the current prices. A price change never expands the USD 1.00 budget.

## 3. Inject the secret and run

Provide `DEEPSEEK_API_KEY` through the process environment without putting its value in a tracked file or command argument. Then run:

```bash
make full-stack
```

The runner allows one direct provider contract smoke and one complete candidate run per attempt. It may start a second attempt only after an HTTP 429, HTTP 5xx, or timeout, and the retry receives a new run ID. A deterministic assertion or identity failure never retries.

The ingestion gate derives its expected chunk count from the durable text blocks produced for the frozen fixtures. It requires F03, F35, F38, and the final enrichment state for every actual block, plus F41 summaries for every fixture document. It does not reuse a fixed chunk count from a different source demo.

## 4. Inspect the candidate

Candidate evidence is written under ignored `.runs/<run_id>/`. A successful candidate includes Run A, Run B, two serialized query records, durable identity, resolver output, model checksums, runtime identity, a cleanup receipt, a pricing snapshot, partial usage visibility, and a candidate manifest.

The candidate is not screenshot-eligible. Human review must accept it before curated evidence can be staged for the viewer. No public cost claim is allowed when usage visibility is partial.

## 5. Cleanup contract

The runner removes only the three namespaces derived from its run ID, stops the dedicated Compose services, releases the three loopback listeners, and removes the ignored runtime config that held the injected secret. It preserves Docker volumes and the downloaded BGE model cache to avoid unrelated or expensive deletion.
