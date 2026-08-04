# Cortrix Demos

Reproducible, evidence-backed, Agent-first demos for Cortrix.

Cortrix Demos is built for Agents to discover, validate, replay, and inspect through stable machine-readable contracts. Humans receive a parallel, readable path through the README, step-by-step guides, and a read-only Web viewer. Both paths resolve to the same accepted evidence; neither path relies on hidden private context.

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

Discover and verify the accepted replay without external calls:

```bash
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
./democtl validate --scenario order-api-field-migration
./democtl verify-accepted
```

Start the read-only viewer:

```bash
make viewer
```

Follow the two human-readable paths:

- [Run A: PostgreSQL/pgvector](scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector.md) explains why the dense-only baseline selects the superseded v1 guide.
- [Run B: Cortrix Full Stack](scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack.md) explains how the Full Stack candidate is produced, checked, and replayed.

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

## Agent-first by design

Agent-first means the executable contract does not begin with an Agent interpreting long prose. A newly cloned repository exposes [agent.json](agent.json) as its root machine entry, then routes the Agent through scenario discovery, description, validation, accepted-evidence verification, and structured errors. The default path is read-only and makes zero external model calls.

This design is intended to earn human trust, not remove human judgment. Humans can read the same business question, technology choices, evidence identity, limitations, and result in ordinary documentation and the Web viewer. Cost-bearing execution, evidence promotion, screenshots, and remote publication remain explicit review boundaries. An Agent may automate a reproducible step, but it cannot silently turn a candidate into accepted evidence or a local result into a public claim.

For a first-time Agent, the discovery order is:

```text
agent.json -> scenarios/registry.json -> scenario.json -> technology profile -> adapter registry -> accepted-run pointer -> run manifest
```

See [Agent quick start](docs/agent-quickstart.md) for the complete safe lifecycle and review boundaries.

## How the repository is organized

The repository separates the business story from the technology used to run it:

```text
agent.json                         Root machine entry and safe bootstrap
scenarios/registry.json            Catalog of available demo scenarios
scenarios/<id>/
  scenario.json                    Business question and frozen assertions
  fixtures/                        Synthetic or curated scenario inputs
  expected/                        Machine-checkable expected outcomes
  profiles/technology-profile.json Scenario-selected database, Cortrix, and LLM stack
  docs/                            Scenario-specific human Run A and Run B guides
  web/                             Scenario presentation copy for the viewer
  evidence/                        Accepted-run pointer and immutable accepted runs
runtime/adapters/                  Reusable database and LLM provider integrations
runtime/config/                    Runtime profiles used by implemented adapters
packages/runner/                   Shared discovery, validation, execution, and cleanup
packages/evidence-schema/          Machine-readable evidence contracts
packages/viewer/                   Read-only human projection of accepted evidence
docs/                              Repository-wide architecture, policy, and authoring guides
config/                            Repository-wide safety and external-call policy
assets/brand/                      Apache-2.0 Cortrix visual identity expressions
```

Each layer has one owner:

- A scenario owns one business question, fixtures, assertions, presentation text, and scenario-specific guides.
- A technology profile selects the database baseline, Cortrix identity, embedding and reranker models, and optional LLM provider for that scenario.
- An adapter owns reusable integration code and capability checks. It does not own a scenario answer.
- An accepted run freezes exact source, model, provider, resolver, cleanup, cost-visibility, and screenshot identity.

When a new demo is added, create a new `scenarios/<id>/` vertical slice and register it. Reuse an existing implemented adapter when possible. If the scenario needs Elasticsearch, MongoDB, or another LLM, add or implement that adapter separately and select it only in that scenario's technology profile. Do not replace the technology globally, duplicate adapters inside scenarios, or overwrite prior accepted evidence.

The complete rules live in [Repository architecture](docs/architecture.md), [Technology profiles](docs/technology-profiles.md), and [Authoring a demo](docs/authoring-a-demo.md).

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

Before adding a scenario, follow [Agent quick start](docs/agent-quickstart.md), [Repository architecture](docs/architecture.md), [Technology profiles](docs/technology-profiles.md), and [Authoring a demo](docs/authoring-a-demo.md).

## Status boundaries

- Cortrix target release for the accepted first scenario: `v1.0.0-rc.1`
- Validated source revision: `32b82f6f8f1d7a41349f408969ff03b7997b6c15`
- Current accepted provider/model: `deepseek/deepseek-v4-flash`
- Local generative fallback: prohibited
- GitHub Actions, Pages, releases, forks, remote localization branches, and public visibility: not configured
