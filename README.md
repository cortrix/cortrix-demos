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

`verify-accepted` proves `proof_scope: archive_integrity`: the tracked pointer, manifest, checksums, source identity, assertions, cleanup receipt, and screenshot bindings agree and remain unmodified. It reports `live_reexecution: false`; it does not rerun PostgreSQL, Cortrix, retrieval, or an LLM. Use the manual Runbooks or an explicitly authorized live run when you need to prove current reproducibility.

Start the read-only viewer:

```bash
make viewer
```

The viewer tries the preferred local preview address and prints the address it actually uses. To force loopback or choose another port, run `make viewer VIEWER_BIND=127.0.0.1 VIEWER_PORT=18765`.

Follow the two human-readable paths:

- [Run A: PostgreSQL/pgvector](scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector.md) explains why the dense-only baseline selects the superseded v1 guide.
- [Run B: Cortrix Full Stack](scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack.md) explains how the Full Stack candidate is produced, checked, and replayed.
- [Run A Manual Runbook: PostgreSQL and pgvector](scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector-step-by-step.md) provides copy-and-paste Docker, HTTP, Python, and SQL commands for operating the baseline directly, without `democtl`.
- [Run B Manual Runbook: Cortrix Full Stack](scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack-step-by-step.md) provides the matching copy-and-paste Docker, HTTP, and Python commands for configuring and querying Cortrix directly, without `democtl`.

A manual live run is separate. Read the [Full Stack runbook](docs/full-stack-runbook.md) before using `preflight`. Its explicit preparation path clones the pinned Cortrix source and runs `./democtl prepare-image --scenario order-api-field-migration`; the command reuses a matching local image and builds from the pinned source only when the image is absent. Missing secrets, unsupported adapters, source drift, model drift, pricing drift, or budget failure stops before external work. The repository-wide ceiling for new authorized execution is `USD 1.00`.

## Inspect the evidence

Start with:

- [Scenario registry](scenarios/registry.json)
- [Technology profile](scenarios/order-api-field-migration/profiles/technology-profile.json)
- [Accepted-run pointer](scenarios/order-api-field-migration/evidence/accepted-run.json)
- [Evidence policy](docs/evidence-policy.md)
- [Run manifest schema](packages/evidence-schema/run-manifest.schema.json)
- [Repository architecture](docs/architecture.md)

Candidate runs stay in the ignored `.runs/` directory. Only independently accepted, sanitized evidence is promoted under a scenario's tracked `evidence/runs/` directory. Existing accepted evidence remains immutable historical identity even when shared repository infrastructure evolves.

## Demo observability versus production operation

This repository is designed to let both Agents and humans understand why each result was produced, not merely see the final answer. Agents use the structured `democtl` lifecycle for discovery, reproducibility, fail-closed execution, and evidence generation. Humans can use the paired manual Runbooks to operate the underlying components directly: Run A exposes PostgreSQL/pgvector storage and exact-cosine SQL, while Run B exposes Cortrix configuration, ingestion, retrieval, ranking layers, and lifecycle validation through direct APIs. Both Runbooks use the same frozen fixtures and query and pair copyable commands with real output excerpts.

That level of terminal output is a Demo and audit feature, not a required Cortrix production interface. A production application normally automates embedding, ingestion, vector transfer, query construction, policy validation, and cleanup, and exposes only the business result and the operational telemetry required by its own reliability, privacy, and security policy. It should not copy these educational diagnostics into an end-user response, and it must never expose secrets, raw private content, local paths, or unnecessary provider internals. The manual commands use the underlying PostgreSQL and Cortrix interfaces; the Agent path adds orchestration and sanitized evidence projection without changing those interfaces.

## Agent-first by design

Agent-first means the executable contract does not begin with an Agent interpreting long prose. A newly cloned repository exposes [agent.json](agent.json) as its root machine entry, then routes the Agent through scenario discovery, description, validation, accepted-evidence verification, and structured errors. The default path is read-only and makes zero external model calls.

This design is intended to earn human trust, not remove human judgment. Humans can read the same business question, technology choices, evidence identity, limitations, and result in ordinary documentation and the Web viewer. Cost-bearing execution, evidence promotion, screenshots, and remote publication remain explicit review boundaries. An Agent may automate a reproducible step, but it cannot silently turn a candidate into accepted evidence or a local result into a public claim.

For a first-time Agent, the discovery order is:

```text
agent.json -> scenarios/registry.json -> scenario.json -> scenario validation contract -> technology profile -> adapter registry -> accepted-run pointer -> run manifest
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
  expected/validation.json         Scenario-owned validation and accepted evidence requirements
  profiles/technology-profile.json Scenario-selected database, Cortrix, and LLM stack
  docs/                            Scenario-specific human Run A and Run B guides
  web/                             Scenario presentation copy for the viewer
  evidence/                        Accepted-run pointer and immutable accepted runs
runtime/adapters/                  Reusable database and LLM provider integrations
runtime/config/                    Runtime profiles used by implemented adapters
runtime/image-provenance.json      Local source build and OCI revision contract
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
