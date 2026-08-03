# Authoring a Demo

Each scenario owns its business fixtures, query, profiles, assertions, runbook, locale data, and accepted evidence. Shared packages must not encode business-specific document IDs or lifecycle rules.

Before adding a scenario:

1. Define a narrow business question and responsibility boundary.
2. Record source and license provenance for every input.
3. Freeze scenario, product, and evidence-schema versions separately.
4. Define variable and frozen assertions.
5. Implement a fail-closed candidate run and cleanup receipt.
6. Validate a fresh clone.
7. Complete red-team, blue-team, and human review before accepting evidence.
