# Order API Live Three-Path Comparison

This public, synthetic scenario defines a candidate contract for comparing three independently measured paths over one frozen Order API input set. It does not contain runtime results, screenshots, or accepted evidence.

## Frozen public inputs

The query and four fixture documents are byte-for-byte copies of the public `order-api-field-migration` fixture set in this repository. [`fixtures/manifest.json`](fixtures/manifest.json) records that provenance and each copied file's SHA-256 checksum. The live contract also freezes the complete fixture manifest checksum before execution.

## Deterministic paths

- `a0` performs basic vector retrieval with PostgreSQL and pgvector. It intentionally does not apply application lifecycle rules.
- `a1` adds application-owned lifecycle rules and bounded LLM assistance to the PostgreSQL path.
- `b` uses Cortrix RC2 for processing and retrieval, followed by the same independent application resolver boundary.

DeepSeek Harness compares only `pg`, which binds to `a1`, and `b`. Harness does not run `a0`.

Each path reports the five display stages `input`, `write`, `search`, `result`, and `code`. These presentation totals are separate from the independently measured `ingest` and `query` business operations.

## Source identity

The contract pins Cortrix `v1.0.0-rc.2` at commit `d298d6b7e64c67551f567e7cddd514bae1adb57b` and [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) at commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`.

## Candidate boundary

The current state is `implementation_candidate`. [`packages/live_demo`](../../packages/live_demo/README.md) contains the runtime and Harness adapter, while repository validation remains offline and does not perform a live run. The implementation does not establish provider usage, cost, runtime success, or acceptance.

A future candidate run must report provider request counts, a receipt-based cost estimate and its basis, independent timing, result provenance, cancellation, resume state, and cleanup receipts. Independent review and human acceptance remain separate gates.
