# Cortrix Demos

Reproducible, evidence-backed demos for Cortrix.

This repository is currently a private pre-publication candidate. License selection is pending provenance review. Until a license is selected and published, this repository is not licensed for redistribution.

## First scenario: Order API Field Migration

This constructed scenario isolates a common version-conflict failure mode. A failing payload still uses the retired `account_id` field, while the current API requires `buyer_account_id`.

- Run A is a BGE-M3 dense-only PostgreSQL/pgvector exact-cosine baseline without lifecycle filtering. It follows the failing payload to the superseded v1 guide and selects `account_id`.
- Run B executes the Cortrix Context Full Stack and returns the current v2 migration bulletin with `buyer_account_id` as its final top result.
- The demo application independently applies the lifecycle rule and validates the current Full Stack result as defense in depth.

PostgreSQL and pgvector can filter on lifecycle metadata; this Run A profile intentionally does not. Cortrix supplies multi-path retrieval and ranking evidence. The application owns lifecycle validation. This is a mechanism demo, not a retrieval benchmark or a general superiority claim.

## See the result

Open the [evidence viewer](packages/viewer/README.md) to inspect an accepted-run replay. A replay is a frozen result, not a new live execution. The sealed 2.0.0 scenario does not have an accepted run yet, so the viewer currently fails closed.

The viewer reads the [accepted-run pointer](scenarios/order-api-field-migration/evidence/accepted-run.json). It renders only when the pointer, Run A result, run manifest, layered resolver, and screenshot binding agree with the current scenario contract.

## Run it locally

Requirements:

- Docker and Docker Compose
- Python 3.14
- approximately 1.2 GB for the BGE-M3 and BGE reranker assets
- a user-provided `DEEPSEEK_API_KEY` for a manual Full Stack run

Validate the repository without external calls:

```bash
make validate
```

Run the manual Full Stack preflight:

```bash
./democtl preflight \
  --scenario order-api-field-migration \
  --profile full-stack
```

The runner fails before any external call when the key, pinned source identity, Docker runtime, model checksums, pricing snapshot, or budget contract is missing.

The complete manual procedure is in the [Full Stack runbook](docs/full-stack-runbook.md). It records a candidate, never an accepted run. Acceptance, promotion, and screenshot capture remain separate review-gated steps.

After a candidate passes the private SecondScott Clean Room review, follow the [acceptance and screenshot runbook](docs/acceptance-runbook.md) to stage curated evidence, capture the real viewer, verify screenshot bindings, and test a fresh clone. Final Human Review remains required after the screenshot-backed local package is complete.

## Inspect the evidence

Start with these contracts:

- [Scenario definition](scenarios/order-api-field-migration/scenario.yaml)
- [Expected assertions](scenarios/order-api-field-migration/expected/assertions.json)
- [Layered-ranking contract](docs/layered-ranking-contract.md)
- [Evidence policy](docs/evidence-policy.md)
- [Evidence schema](packages/evidence-schema/run-manifest.schema.json)
- [Compatibility](docs/compatibility.md)
- [Known limitations](docs/known-limitations.md)

Candidate runs stay in the ignored `.runs/` directory. Clean Room-accepted, sanitized evidence is promoted into the scenario's tracked `evidence/runs/` directory only after review; the screenshot-backed package still requires final Human Review.

## Repository structure

```text
packages/
  runner/           Shared execution, validation, and cleanup logic
  viewer/           Read-only accepted-evidence viewer
  evidence-schema/  JSON schemas for manifests and receipts
scenarios/
  order-api-field-migration/
docs/
  Evidence, localization, compatibility, and authoring contracts
```

The official bundle contains only `en-US`. A downstream locale may change presentation, but not execution inputs or raw evidence.

## Status boundaries

- Cortrix target release: `v1.0.0-rc.1`
- Release commit: `e159974f936bd987d5718195d54cd70ff3acc2e5`
- Validated source revision: `32b82f6f8f1d7a41349f408969ff03b7997b6c15`
- External model target: `deepseek-v4-flash`
- Local generative LLM: prohibited
- GitHub Actions, Pages, releases, forks, remote `zh-CN`, and public visibility: not configured
