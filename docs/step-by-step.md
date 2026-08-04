# Human step-by-step guide

This guide uses the accepted replay by default. It does not call an external LLM.

For the detailed operation and evidence checks on each side, use:

- [Run A: PostgreSQL and pgvector](../scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector.md)
- [Run B: Cortrix Full Stack](../scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack.md)
- [Run A Pipeline: Step-by-Step Runbook](../scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector-step-by-step.md)
- [Run B Pipeline: Step-by-Step Runbook](../scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack-step-by-step.md)

## 1. Check the repository

```bash
make validate
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
./democtl verify-accepted
```

You should see one accepted scenario. Its technology profile identifies PostgreSQL/pgvector for Run A, Cortrix for Run B, and DeepSeek V4 Flash for the accepted Full Stack evidence.

## 2. Start the read-only viewer

```bash
make viewer
```

Open `http://192.168.50.75:18765/packages/viewer/index.html`. If that address is unavailable, bind the server to `127.0.0.1` and use the same path.

## 3. Read the result

The comparison shows the same question on both sides:

- Run A selects the superseded v1 guide and `account_id`.
- Run B selects the current v2 bulletin and `buyer_account_id`.
- The application resolver independently validates lifecycle status.

[Open the Agent-first accepted viewer screenshot](../scenarios/order-api-field-migration/evidence/runs/order-api-field-migration-20260804T085505Z/screenshots/cortrix-demo-agent-first-accepted-20260804.png).

## 4. Inspect the evidence

Start with the [accepted pointer](../scenarios/order-api-field-migration/evidence/accepted-run.json), then follow its manifest, Run A result, resolver, and screenshot manifest. The viewer fails closed if their identities disagree.

## 5. Understand the boundary

This is a synthetic mechanism demo, not a retrieval benchmark. PostgreSQL/pgvector can filter lifecycle metadata; this Run A profile intentionally does not. Existing accepted evidence has partial LLM usage visibility and is not a public total-cost claim.

## 6. Run live only when authorized

Read the [Run B guide](../scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack.md) and [Full Stack runbook](full-stack-runbook.md). A live run requires the profile's named secret, pinned source, Docker, model checksums, pricing snapshot, and budget preflight. It produces Run A and Run B as one candidate and must be cleaned up even when rejected.

## 7. Add another demo

Follow [Repository architecture](architecture.md), [Technology profiles](technology-profiles.md), and [Authoring a demo](authoring-a-demo.md). Reuse adapters; do not copy database or provider implementations into a scenario.
