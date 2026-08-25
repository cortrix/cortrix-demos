# Provenance

All repository-owned source, documentation, synthetic fixtures, schemas, and SVG assets are licensed under Apache License 2.0.

| Destination | Source | Owner | License | Notes |
| --- | --- | --- | --- | --- |
| `assets/brand/*.svg` | Cortrix Magma Orange VI specification | Cortrix contributors | Apache-2.0 | Newly expressed SVG source for this repository; trademark rights remain separate |
| `scenarios/order-api-field-migration/fixtures/*` | Synthetic API migration scenario | Cortrix contributors | Apache-2.0 | Constructed data; not copied from customer or private production data |
| `scenarios/database-change-conflict-guardian/fixtures/*` | Synthetic database migration conflict scenario | Cortrix contributors | Apache-2.0 | Constructed data; not copied from customer or production data |
| `scenarios/api-version-drift-coding-agent/fixtures/*` | Synthetic SDK version drift scenario | Cortrix contributors | Apache-2.0 | Constructed data; not copied from a partner repository |
| `scenarios/payment-incident-shift-handoff/fixtures/*` | Synthetic incident handoff scenario | Cortrix contributors | Apache-2.0 | Constructed data; not copied from an incident or customer system |
| `scenarios/migration-decision-recovery/fixtures/*` | Synthetic migration decision and event-position scenario | Cortrix contributors | Apache-2.0 | Constructed data; the event export is application-owned demo input |
| `packages/*`, `runtime/*`, `tests/*` | New Cortrix Demos implementation | Cortrix contributors | Apache-2.0 | No legacy demo repository history copied |
| Accepted screenshot PNG files | Read-only viewer rendering accepted evidence | Cortrix contributors | Apache-2.0 | Browser capture; not generated or manually edited |

The DeepSeek Harness adapter source belongs to the separately governed Cortrix Integrations repository. Cortrix source code, DeepSeek Harness, model weights, PostgreSQL, pgvector, Docker images, and hosted LLM services are referenced or invoked at runtime and are not redistributed by this repository. Review their exact revisions, licenses, and terms before use.
