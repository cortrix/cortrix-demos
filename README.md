# Cortrix Demos

Reproducible, evidence-backed, Agent-first demos for Cortrix.

Cortrix Demos is built for Agents to discover, validate, replay, and inspect through stable machine-readable contracts. Humans receive a parallel, readable path through the README, step-by-step guides, and a read-only Web viewer. Both paths resolve to the same accepted evidence; neither path relies on hidden private context.

This repository is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for Cortrix visual identity and trademark attribution.

## See the result

Open the [evidence viewer](packages/viewer/README.md) or follow the [human step-by-step guide](docs/step-by-step.md) to inspect the accepted local replay. The sealed run passed Clean Room review and screenshot verification. The viewer fails closed when its pointer, manifest, Run A result, resolver, or screenshot identity disagrees.

The accepted first scenario is a synthetic mechanism demo: Run A selects the superseded v1 API field, while Cortrix Full Stack returns and validates the current v2 field. Four DeepSeek Harness plugin scenarios are also independently accepted: database conflict, API version drift, payment incident handoff, and migration decision recovery. None of these scenarios is a retrieval benchmark or a general superiority claim.

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
./democtl describe --scenario database-change-conflict-guardian --json
./democtl validate --scenario database-change-conflict-guardian
./democtl describe --scenario api-version-drift-coding-agent --json
./democtl validate --scenario api-version-drift-coding-agent
./democtl verify-accepted
```

`verify-accepted` proves `proof_scope: archive_integrity`: the tracked pointer, manifest, checksums, source identity, assertions, cleanup receipt, and screenshot bindings agree and remain unmodified. It reports `live_reexecution: false`; it does not rerun PostgreSQL, Cortrix, retrieval, or an LLM. Use the manual Runbooks or an explicitly authorized live run when you need to prove current reproducibility.

Start the read-only viewer:

```bash
make viewer
```

The viewer tries the preferred local preview address and prints the address it actually uses. To force loopback or choose another port, run `make viewer VIEWER_BIND=127.0.0.1 VIEWER_PORT=18765`.

## Inspect the evidence

Start with:

- [Scenario registry](scenarios/registry.json)
- [Technology profile](scenarios/order-api-field-migration/profiles/technology-profile.json)
- [Accepted-run pointer](scenarios/order-api-field-migration/evidence/accepted-run.json)
- [Operational continuity Clean Room evidence](docs/operational-continuity-clean-room-evidence.md)
- [DeepSeek Harness integration](docs/deepseek-harness-integration.md)
- [DeepSeek Harness limitations](docs/deepseek-harness-limitations.md)
- [Evidence policy](docs/evidence-policy.md)
- [Run manifest schema](packages/evidence-schema/run-manifest.schema.json)
- [Repository architecture](docs/architecture.md)

Candidate runs stay in the ignored `.runs/` directory. Only independently accepted, sanitized evidence is promoted under a scenario's tracked `evidence/runs/` directory. Existing accepted evidence remains immutable historical identity even when shared repository infrastructure evolves.

An authorized local reviewer may inspect one completed candidate without promoting it by running `make viewer-candidate-qa RUN_ID=<run_id>`. This starts a separate, server-gated route that verifies the candidate still reports `screenshot_eligible=false` and `human_review_required=true`, and labels the page as Candidate QA rather than accepted evidence. Browser captures from that route are review artifacts only; `record-screenshot` refuses them, and the accepted viewer remains unchanged.

Follow the two human-readable paths:

- [Run A: PostgreSQL/pgvector](scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector.md) explains why the dense-only baseline selects the superseded v1 guide.
- [Run B: Cortrix Full Stack](scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack.md) explains how the Full Stack candidate is produced, checked, and replayed.
- [Run A Manual Runbook: PostgreSQL and pgvector](scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector-step-by-step.md) provides copy-and-paste Docker, HTTP, Python, and SQL commands for operating the baseline directly, without `democtl`.
- [Run B Manual Runbook: Cortrix Full Stack](scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack-step-by-step.md) provides the matching copy-and-paste Docker, HTTP, and Python commands for configuring and querying Cortrix directly, without `democtl`.

The DeepSeek Harness integration adds four scenario slices with the same Agent-first and human-readable ownership model:

- [Database Change Conflict Guardian](scenarios/database-change-conflict-guardian/README.md) compares incomplete frozen workspace evidence with evidence retrieved through the read-only Cortrix bundle before a database action is considered.
- [API Version Drift Coding Agent](scenarios/api-version-drift-coding-agent/README.md) compares an obsolete SDK retry example with the current API, deprecation notice, migration guide, and maintained tests.
- [Payment Incident Shift Handoff](scenarios/payment-incident-shift-handoff/README.md) compares a superseded shift snapshot with the current handoff, ruled-out database hypothesis, pending remediation, and read-only checks.
- [Migration Decision Recovery](scenarios/migration-decision-recovery/README.md) compares an obsolete option B recommendation with the final option C decision across front, middle, and end event positions.

Read the [integration architecture and source preparation](docs/deepseek-harness-integration.md), [use cases](docs/deepseek-harness-use-cases.md), [limitations](docs/deepseek-harness-limitations.md), [model asset boundary](docs/model-assets.md), and [legacy evidence policy](docs/legacy-evidence.md) before attempting a new live campaign.

After a Harness scenario has an independently accepted run, open its evidence projection with `make viewer-harness SCENARIO=<scenario-id>`. The server prints the exact accepted-only route. It refuses a candidate or an identity mismatch before serving the page.

All four Harness scenarios use the exact same Harness, model, question, corpus, non-Cortrix tools, answer contract, and resolver across Run A and Run B. The only independent variable is whether the Cortrix bundle supplies evidence. Plugin retrieval and application authority remain separate, and a no-difference or reverse result must be retained instead of tuned away.

A manual live run is separate. Read the [Full Stack runbook](docs/full-stack-runbook.md) before using `preflight`. Its explicit preparation path clones the pinned Cortrix source and runs `./democtl prepare-image --scenario order-api-field-migration`; the command reuses a matching local image and builds from the pinned source only when the image is absent. Missing secrets, unsupported adapters, source drift, model drift, pricing drift, or budget failure stop the run before external work. The generic direct Full Stack path keeps a `USD 1.00` ceiling. A reviewed Harness campaign owns its own explicit ceiling; the accepted operational-continuity campaign used `USD 5.00` and remained far below that bound.

The current public-release candidate is replay-ready but not live-reproduction-ready because the Cortrix Integrations repository is not public yet and the archived results bind an earlier integration commit. The exact BGE asset sources, revisions, sizes, checksums, licenses, and fail-closed preparation commands are now documented publicly. A new live campaign must still use the final public integration commit and pass a new independent clean-room review.

For authorized workstation runs, the runner can use a protected user-level `current.yaml` LLM profile instead of requiring the operator to export a real API key for every command. Explicit environment injection remains the highest-priority option for CI and containers. Safe discovery, validation, accepted replay, tests, and the viewer never read the profile; only a cost-bearing Full Stack preflight may resolve it. The profile stays outside every Git checkout, and runtime output records only its source class. See [Secret injection and default profiles](docs/full-stack-runbook.md#3-inject-the-secret-and-run) for setup and permission requirements.

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

See [Agent quick start](docs/agent-quickstart.md) for the complete safe lifecycle and review boundaries. The [Agent error contract](docs/agent-error-contract.md) defines when an Agent may correct input or retry and when it must stop without changing evidence.

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
packages/viewer/                   Read-only accepted viewer and isolated local Candidate QA projection
docs/                              Repository-wide architecture, policy, and authoring guides
config/                            Repository-wide safety and external-call policy
assets/brand/                      Apache-2.0 Cortrix visual identity expressions
```

Each layer has one owner:

- A scenario owns one business question, fixtures, assertions, presentation text, and scenario-specific guides.
- A technology profile selects the database baseline, Cortrix identity, embedding and reranker models, and optional LLM provider for that scenario.
- An adapter owns reusable integration code and capability checks. It does not own a scenario answer.
- An accepted run freezes exact source, model, provider, resolver, cleanup, cost-visibility, and screenshot identity.

Harness-based scenarios also freeze the Harness commit, plugin commit, tool schema, shared answer prompt template, and the `cortrix_bundle_loaded` comparison variable. Their candidate and accepted manifests use [the Harness comparison evidence schema](packages/evidence-schema/harness-run-manifest.schema.json); the original scenario continues to use its historical schema without semantic changes.

The Agent entry for this integration is `agent.json -> gates.deepseek_harness`. It names the safe discovery commands, reviewed campaign contracts, the exact two-tool surface, the independent acceptance gate, and the accepted viewer entry. Safe discovery never reads the LLM profile or starts Cortrix.

Four Harness scenarios now cover database conflict, API drift, incident handoff, and long-task decision recovery. The first two use the foundation campaign. Payment incident handoff and migration decision recovery use the operational continuity campaign; the migration scenario runs the same comparison with the decisive event at the front, middle, and end of a 30-event explicit application-owned export. These exports are frozen demo input, not automatic Cortrix memory.

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
- Repository visibility: public
- GitHub Actions, Pages, and releases: not configured
- The official repository ships only `en-US`; maintained downstream localizations must preserve the accepted evidence identity
