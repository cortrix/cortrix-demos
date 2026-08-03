# Cortrix Demos

Reproducible, evidence-backed demos for Cortrix.

This repository is currently a private pre-publication candidate. License selection is pending provenance review. Until a license is selected and published, this repository is not licensed for redistribution.

## First scenario: Order API Field Migration

An outdated integration guide receives the highest BGE cross-encoder rerank score, but that score is only one layer of the Full Stack result. The demo keeps each ranking responsibility explicit:

- Run A records a dense BGE-M3 exact-cosine baseline, where the current v2 release note ranks first.
- Run B exposes the superseded v1 guide as the BGE cross-encoder leader, then records the current v2 release note as the final top result after DeepSeek listwise reranking.
- The demo application independently applies the lifecycle rule and preserves the current final top result as defense in depth.

The phrase “most similar” in this scenario title refers specifically to the highest BGE cross-encoder rerank score, not the dense baseline or the final response order. Cortrix supplies ranking evidence. The application owns lifecycle validation.

## See the result

Open the [evidence viewer](packages/viewer/README.md) to inspect an accepted-run replay. A replay is a frozen result, not a new live execution.

No accepted English run is published in this bootstrap yet. The viewer fails closed until an accepted run is present.

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

The complete manual procedure is in the [Full Stack runbook](docs/full-stack-runbook.md). It records a candidate, never an accepted run. Acceptance, promotion, and screenshot capture remain separate human-review steps.

After a candidate passes private Human Review, follow the [acceptance and screenshot runbook](docs/acceptance-runbook.md) to stage curated evidence, capture the real viewer, verify screenshot bindings, and test a fresh clone.

## Inspect the evidence

Start with these contracts:

- [Scenario definition](scenarios/order-api-field-migration/scenario.yaml)
- [Expected assertions](scenarios/order-api-field-migration/expected/assertions.json)
- [Layered-ranking contract](docs/layered-ranking-contract.md)
- [Evidence policy](docs/evidence-policy.md)
- [Evidence schema](packages/evidence-schema/run-manifest.schema.json)
- [Compatibility](docs/compatibility.md)
- [Known limitations](docs/known-limitations.md)

Candidate runs stay in the ignored `.runs/` directory. Human-accepted, sanitized evidence is promoted into the scenario's tracked `evidence/runs/` directory only after review.

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
