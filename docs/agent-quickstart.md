# Agent quick start

This repository is designed so an Agent can discover and inspect a demo without private workspace knowledge.

## Bootstrap from the repository root

Read [`agent.json`](../agent.json) first. It is the stable machine entry for the safe default, catalogs, lifecycle, and human-intervention gates. Root [`AGENTS.md`](../AGENTS.md) gives contributor constraints, but the bootstrap does not depend on an Agent already knowing Cortrix conventions.

Run the `bootstrap.safe_default` commands in order:

```bash
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
./democtl validate --scenario order-api-field-migration
./democtl verify-accepted
```

This path is read-only and reports `external_calls: 0`. Do not infer authorization for a live run from the presence of a provider profile or secret environment variable.

## Discover

```bash
./democtl list --json
```

The response lists scenario IDs, status, technology-profile path, accepted-evidence pointer, and human guide.

## Describe

```bash
./democtl describe --scenario order-api-field-migration --json
```

The response resolves the business contract, baseline adapter, Cortrix identity, LLM provider/model/roles, required secret name, support status, accepted evidence, and lifecycle endpoints.

## Validate without external calls

```bash
./democtl validate --scenario order-api-field-migration
./democtl public-safety
```

Both commands emit JSON. A failure emits a structured error containing `code`, `category`, `retryable`, `message`, and `structured_data`. Retryable failures also include `retry_after_ms`; `structured_data.next_action` gives a safe recovery action without exposing a secret or local absolute path.

`verify-accepted` returns `proof_scope: archive_integrity` and `live_reexecution: false`. It verifies the tracked evidence package and does not claim that retrieval was rerun today.

## Agent lifecycle

```text
discover -> describe -> validate -> preflight -> provision -> run -> inspect -> verify -> cleanup
```

The accepted replay requires no external model call. A live Full Stack run is manual, reads its secret only from the named environment variable, and produces a candidate rather than accepted evidence.

## Contract discovery order

```text
agent.json
  -> scenarios/registry.json
  -> scenarios/<id>/scenario.json
  -> scenarios/<id>/expected/validation.json
  -> scenarios/<id>/profiles/technology-profile.json
  -> runtime/adapters/registry.json
  -> scenarios/<id>/evidence/accepted-run.json
  -> accepted run manifest
```

Use the scenario contract for the business question and assertions, the technology profile for scenario-specific database and LLM selection, the adapter registry for implemented capability, and the accepted pointer for immutable evidence identity. Never derive runtime support from prose or a `contract_only` adapter entry.

Before an authorized live run, follow `gates.live_full_stack.source_preparation` and `gates.live_full_stack.image_preparation` in `agent.json`. Image provenance is machine-readable at `runtime/image-provenance.json`. Preparation makes no model call, reuses a matching local image, and otherwise builds from the pinned source revision.

## Extension boundary

To add a demo, create a new scenario vertical slice and register it. Reuse shared adapters; do not place database or provider integration code inside a scenario. Changing the database or LLM for one scenario means selecting a different implemented adapter in that scenario's technology profile, not replacing a repository-wide stack.

Read [Repository architecture](architecture.md), [Technology profiles](technology-profiles.md), and [Authoring a demo](authoring-a-demo.md) before editing.

## Review boundary

An Agent can discover, validate, run, inspect, verify, and clean up. Independent Clean Run acceptance remains a separate review gate; remote publication remains human-governed. The Web viewer renders the same accepted evidence contract for human readers.
