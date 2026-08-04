# Cortrix Demos

Reproducible, evidence-backed, Agent-first demos for Cortrix.

An Agent can discover each scenario, resolve its database and LLM technology profile, validate contracts, inspect accepted evidence, and decide whether a failure is retryable without parsing prose. Humans see the same accepted evidence through concise documentation and a read-only Web viewer.

This repository is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for Cortrix visual identity and trademark attribution.

## See the result

Open the [evidence viewer](packages/viewer/README.md) or follow the [human step-by-step guide](docs/step-by-step.md) to inspect the accepted local replay. The sealed run passed Clean Room review and screenshot verification. The viewer fails closed when its pointer, manifest, Run A result, resolver, or screenshot identity disagrees.

The first scenario is a synthetic mechanism demo: Run A selects the superseded v1 API field, while Cortrix Full Stack returns and validates the current v2 field. It is not a retrieval benchmark or a general superiority claim.

## Run it locally

Requirements:

- Python 3.14 for validation and discovery
- Docker and Docker Compose only for a live Full Stack run
- approximately 1.2 GB for the BGE-M3 and BGE reranker assets only for live execution
- the technology profile's named API key only for an explicitly authorized live run

Discover the repository without external calls:

```bash
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
make validate
```

Start the read-only viewer:

```bash
make viewer
```

A manual live run is separate. Read the [Full Stack runbook](docs/full-stack-runbook.md) before using `preflight`. Missing secrets, unsupported adapters, source drift, model drift, pricing drift, or budget failure stops before external work. The repository-wide ceiling for new authorized execution is `USD 1.00`.

## Inspect the evidence

Start with:

- [Scenario registry](scenarios/registry.json)
- [Technology profile](scenarios/order-api-field-migration/profiles/technology-profile.json)
- [Accepted-run pointer](scenarios/order-api-field-migration/evidence/accepted-run.json)
- [Evidence policy](docs/evidence-policy.md)
- [Run manifest schema](packages/evidence-schema/run-manifest.schema.json)
- [Repository architecture](docs/architecture.md)

Candidate runs stay in the ignored `.runs/` directory. Only independently accepted, sanitized evidence is promoted under a scenario's tracked `evidence/runs/` directory. Existing accepted evidence remains immutable historical identity even when shared repository infrastructure evolves.

## First scenario: Order API Field Migration

The constructed corpus isolates a common version-conflict failure mode. A failing payload still uses the retired `account_id` field, while the current API requires `buyer_account_id`.

- Run A is a BGE-M3 dense-only PostgreSQL/pgvector exact-cosine baseline without lifecycle filtering. It follows the failing payload to the superseded v1 guide.
- Run B executes Cortrix Context Full Stack and returns the current v2 migration bulletin as its final top result.
- The demo application independently validates lifecycle status as defense in depth.

PostgreSQL and pgvector can filter lifecycle metadata; this Run A profile intentionally does not. Cortrix supplies multi-path retrieval and ranking evidence. The application owns lifecycle validation.

## Extend the demos

The core ownership chain is:

```text
scenario -> technology profile -> reusable adapter -> immutable accepted run
```

Business fixtures and assertions stay under `scenarios/<id>/`. Reusable database and provider integrations stay under `runtime/adapters/` and shared runner code. A scenario may select PostgreSQL/pgvector, Elasticsearch, MongoDB, DeepSeek, or an OpenAI mini model only when the selected adapters are implemented and tested; `contract_only` entries are documentation, not runnable claims.

Read [Repository architecture](docs/architecture.md), [Technology profiles](docs/technology-profiles.md), [Agent quick start](docs/agent-quickstart.md), and [Authoring a demo](docs/authoring-a-demo.md) before adding a scenario.

## Status boundaries

- Cortrix target release for the accepted first scenario: `v1.0.0-rc.1`
- Validated source revision: `32b82f6f8f1d7a41349f408969ff03b7997b6c15`
- Current accepted provider/model: `deepseek/deepseek-v4-flash`
- Local generative fallback: prohibited
- GitHub Actions, Pages, releases, forks, remote localization branches, and public visibility: not configured
