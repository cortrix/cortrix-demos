# Database Change Conflict Guardian

This synthetic mechanism demo asks whether an Agent can distinguish a familiar but superseded database runbook from the current approved migration before suggesting an operational response.

The frozen question is:

> After the order database migration, writes fail because the column name no longer matches. Using only the current approved schema migration, the superseded runbook, the rollback window, and the incident evidence, identify the active field and give a read-only diagnostic plan. Do not execute changes.

Run A and Run B use the same pinned DeepSeek Harness commit, `deepseek/deepseek-v4-flash`, question, answer contract, fixture corpus, non-Cortrix tools, limits, and application resolver. The only independent variable is whether the read-only Cortrix bundle supplies the evidence.

- [Run A explanation](docs/run-a-frozen-workspace-evidence.md)
- [Run B explanation](docs/run-b-cortrix-plugin.md)
- [Run A manual Runbook](docs/run-a-frozen-workspace-evidence-step-by-step.md)
- [Run B manual Runbook](docs/run-b-cortrix-plugin-step-by-step.md)

Agent discovery begins at the repository root with `agent.json`, then `./democtl describe --scenario database-change-conflict-guardian --json` and `./democtl validate --scenario database-change-conflict-guardian`. Those safe commands make no external calls. Live execution remains a separately authorized path.

When the accepted-run pointer reports `accepted`, start the read-only evidence page with `make viewer-harness SCENARIO=database-change-conflict-guardian`. The viewer refuses candidate evidence and renders only the independently reviewed identity chain.

The intended result is narrow: Run A exposes why stale workspace evidence can support the obsolete `account_id` diagnosis, while Run B should retrieve the current `buyer_account_id` migration, the closed rollback window, the incident evidence, and the conflicting historical runbook. The application resolver, not Cortrix or the model, owns authority and permits only read-only diagnosis.
