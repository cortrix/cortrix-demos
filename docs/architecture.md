# Repository architecture

Cortrix Demos separates the business story from the technology used to demonstrate it.

```text
scenario -> technology profile -> reusable adapter -> immutable accepted run
```

## Directory map

```text
agent.json          Root machine entry, safe bootstrap, catalogs, and review gates
assets/brand/       Apache-2.0 SVG expressions of the Cortrix visual identity
config/             Repository-wide safety and external-call policy
docs/               Agent and human guides, evidence policy, and extension rules
packages/runner/    Shared discovery, validation, execution, and cleanup code
packages/viewer/    Read-only human projection of accepted evidence
packages/evidence-schema/  Machine-readable accepted-evidence contracts
runtime/adapters/   Reusable baseline and LLM provider implementations
runtime/config/     Cortrix runtime profiles used by implemented adapters
runtime/harness/    Pinned Harness campaign, fixture loading, read-only plugin query, and answer orchestration
scenarios/registry.json  Machine-readable scenario discovery entry
scenarios/<id>/     Business contract, fixtures, assertions, technology profile, human run guides, web text, and evidence
```

A scenario vertical slice uses this internal layout:

```text
scenarios/<id>/
  scenario.json
  fixtures/
  expected/
  expected/validation.json
  profiles/technology-profile.json
  docs/
  web/
  evidence/accepted-run.json
  evidence/runs/<run_id>/
```

## Ownership rules

- A scenario owns one business question, fixtures, expected assertions, presentation text, and accepted evidence.
- A scenario validation contract owns that scenario's sealed identity, assertion requirements, runtime paths, and accepted evidence rules. Shared packages load it instead of assuming the first scenario's values.
- Scenario-specific Run A and Run B documentation stays in `scenarios/<id>/docs/`; repository-wide execution and policy documents stay in `docs/`.
- A technology profile selects one baseline adapter, one Cortrix identity, and optional LLM adapters for that scenario.
- An adapter owns reusable integration code and capability checks. It never owns a scenario answer.
- An accepted run freezes exact versions, model identities, source revision, cost visibility, resolver output, cleanup, and screenshot bindings.
- Changing a database or model creates a new profile and run. It does not overwrite accepted evidence.

The first scenario retains `full-stack` and `replay` compatibility profiles because its accepted evidence predates the adapter catalog. New scenarios should use the technology-profile contract directly.

DeepSeek Harness scenarios use the same vertical-slice ownership with one additional frozen chain: Harness commit, standalone plugin commit, exact two-tool surface, answer prompt contract, comparison variable, durable tool events, and independent Clean Room record. Raw Harness home and session storage stay ignored; only curated, public-safe evidence enters `evidence/runs/<run_id>/`.

## Extension order

1. Read `agent.json`, this architecture guide, the technology-profile guide, and the authoring guide.
2. Add or reuse an implemented adapter.
3. Add the scenario vertical slice and technology profile.
4. Register the scenario in `scenarios/registry.json`.
5. Add fixtures, assertions, tests, Run A and Run B human documentation, and viewer projection.
6. Run local validation before any external call.
7. Produce a candidate, obtain independent Clean Run acceptance, and capture the accepted viewer.

Never claim that a `contract_only` adapter is runnable. A new adapter becomes `implemented` only with code, fail-closed tests, cleanup, and fresh-clone validation.
