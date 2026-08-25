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

Both commands emit JSON. A failure emits a structured error containing `code`, `category`, `retryable`, `message`, and `structured_data`. Retryable failures also include `retry_after_ms`; `structured_data.next_action` appears only when a safe corrective action exists. Evidence integrity, deterministic assertion, and invalid internal state errors deliberately omit `next_action`, which means the Agent must stop and surface the failure. See the [Agent error contract](agent-error-contract.md) for the decision matrix.

`verify-accepted` returns `proof_scope: archive_integrity` and `live_reexecution: false`. It verifies the tracked evidence package and does not claim that retrieval was rerun today.

## Agent lifecycle

```text
discover -> describe -> validate -> preflight -> provision -> run -> inspect -> verify -> cleanup
```

The accepted replay requires no external model call. A live Full Stack run is manual and produces a candidate rather than accepted evidence. After authorization reaches preflight, the runner resolves the declared secret from the named environment variable, an absolute profile selected by `CORTRIX_LLM_SECRET_FILE`, or the protected user default at `${XDG_CONFIG_HOME:-$HOME/.config}/cortrix/secrets/llm/current.yaml`, in that order. An Agent must not read or print the profile itself. Preflight records only the source class, and discovery, validation, replay, tests, and the viewer never resolve the secret.

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

If `integration_kind` is `deepseek_harness_cortrix_readonly`, continue through `agent.json -> gates.deepseek_harness`. The safe commands there describe and validate all four Harness scenarios without reading a secret. Only an explicitly authorized execution may run `./democtl harness campaign`; it checks the frozen Harness, integration, Cortrix source, image, model cache, pricing, budget, required runtime exports, and a keyless Headless profile load before the shared contract smoke or answer calls. The keyless load uses `--help`, removes provider credentials from its environment, disables telemetry, and must create no session artifact. The runner then starts the fixed Cortrix runtime and performs a zero-LLM source projection probe: it loads frozen evidence into an isolated namespace, calls the real two-tool integration, verifies each returned content hash, binds each normalized source block to exactly one frozen fixture, and removes the probe namespace. A probe failure stops the campaign before the DeepSeek profile is read or a paid call begins. Curated usage records a stable session artifact kind and SHA-256, while the raw session path remains ignored runtime data. A successful campaign still produces candidates. `record-clean-room-pass`, `stage-accepted`, `record-screenshot`, and the accepted viewer are separate identity gates.

Before an authorized live run, follow `gates.live_full_stack.source_preparation` and `gates.live_full_stack.image_preparation` in `agent.json`. Image provenance is machine-readable at `runtime/image-provenance.json`. Preparation makes no model call, reuses a matching local image, and otherwise builds from the pinned source revision.

## Extension boundary

To add a demo, create a new scenario vertical slice and register it. Reuse shared adapters; do not place database or provider integration code inside a scenario. Changing the database or LLM for one scenario means selecting a different implemented adapter in that scenario's technology profile, not replacing a repository-wide stack.

Read [Repository architecture](architecture.md), [Technology profiles](technology-profiles.md), and [Authoring a demo](authoring-a-demo.md) before editing.

## Review boundary

An Agent can discover, validate, run, inspect, verify, and clean up. Independent Clean Run acceptance remains a separate review gate; remote publication remains human-governed. The Web viewer renders the same accepted evidence contract for human readers.
