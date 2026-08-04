# Repository architecture

Cortrix Demos separates the business story from the technology used to demonstrate it.

```text
scenario -> technology profile -> reusable adapter -> immutable accepted run
```

## Directory map

```text
assets/brand/       Apache-2.0 SVG expressions of the Cortrix visual identity
config/             Repository-wide safety and external-call policy
docs/               Agent and human guides, evidence policy, and extension rules
packages/runner/    Shared discovery, validation, execution, and cleanup code
packages/viewer/    Read-only human projection of accepted evidence
packages/evidence-schema/  Machine-readable accepted-evidence contracts
runtime/adapters/   Reusable baseline and LLM provider implementations
runtime/config/     Cortrix runtime profiles used by implemented adapters
scenarios/registry.json  Machine-readable scenario discovery entry
scenarios/<id>/     Business fixtures, assertions, profiles, web text, and evidence
```

## Ownership rules

- A scenario owns one business question, fixtures, expected assertions, presentation text, and accepted evidence.
- A technology profile selects one baseline adapter, one Cortrix identity, and optional LLM adapters for that scenario.
- An adapter owns reusable integration code and capability checks. It never owns a scenario answer.
- An accepted run freezes exact versions, model identities, source revision, cost visibility, resolver output, cleanup, and screenshot bindings.
- Changing a database or model creates a new profile and run. It does not overwrite accepted evidence.

The first scenario retains `full-stack` and `replay` compatibility profiles because its accepted evidence predates the adapter catalog. New scenarios should use the technology-profile contract directly.

## Extension order

1. Add or reuse an implemented adapter.
2. Add the scenario and technology profile.
3. Register the scenario in `scenarios/registry.json`.
4. Add fixtures, assertions, tests, human documentation, and viewer projection.
5. Run local validation before any external call.
6. Produce a candidate, obtain independent Clean Run acceptance, and capture the accepted viewer.

Never claim that a `contract_only` adapter is runnable. A new adapter becomes `implemented` only with code, fail-closed tests, cleanup, and fresh-clone validation.
