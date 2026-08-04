# Authoring a demo

Each scenario owns one business question, fixtures, query, assertions, presentation, and accepted evidence. Shared packages and runtime adapters must not encode business-specific document IDs, expected fields, or lifecycle answers.

## Before implementation

1. Define a narrow business question and responsibility boundary.
2. Choose existing implemented baseline and provider adapters, or implement new adapters first.
3. Record Apache-2.0-compatible provenance for every repository-owned input and document external component terms.
4. Freeze scenario, technology-profile, product, and evidence-schema versions separately.
5. Define variable output and deterministic assertions without hiding unfavorable evidence.
6. Register the scenario in `scenarios/registry.json`.
7. Add separate human Run A and Run B guides that explain the same machine contract and evidence boundary.

## Required scenario structure

```text
scenarios/<scenario-id>/
  README.md
  scenario.json
  profiles/technology-profile.json
  fixtures/
  expected/
  docs/
    run-a-<baseline>.md
    run-b-cortrix-full-stack.md
  web/
  evidence/
```

Compatibility profile files may remain when required to verify historical evidence, but new implementation choices belong in the technology profile.

The root `agent.json` remains the repository bootstrap and should not be duplicated per scenario. A new scenario becomes Agent-discoverable through `scenarios/registry.json`; its scenario contract, technology profile, adapter support, human guides, and accepted pointer must all resolve from that registry entry.

## Acceptance

1. Run discovery, catalog, fixture, schema, and public-safety validation with zero external calls.
2. Run live only when explicitly authorized and within the repository cost policy.
3. Produce a candidate and cleanup receipt.
4. Obtain independent Clean Run acceptance.
5. Promote only curated evidence, render it through the read-only viewer, and capture a real browser screenshot.
6. Validate an exact-commit fresh clone.
7. Confirm that an unfamiliar Agent can start from `agent.json` and that an unfamiliar human can reach both scenario run guides from `README.md`.

See [Repository architecture](architecture.md) and [Technology profiles](technology-profiles.md) for extension contracts.
