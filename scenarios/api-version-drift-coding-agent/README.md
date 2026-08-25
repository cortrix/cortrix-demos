# API Version Drift Coding Agent

This synthetic mechanism demo asks whether an Agent can distinguish a familiar but obsolete SDK retry example from the current official API after a major-version upgrade.

The frozen question is:

> After upgrading the Orders SDK from version 1.x to 2.x, retry behavior no longer matches the old example. Find the current official API and deprecation notice, explain why the example is obsolete, and propose the smallest test plan. Do not edit code.

Run A and Run B use the same pinned DeepSeek Harness commit, `deepseek/deepseek-v4-flash`, question, answer contract, fixture corpus, non-Cortrix tools, limits, and application resolver. The only independent variable is whether the read-only Cortrix bundle supplies the evidence.

- [Run A explanation](docs/run-a-frozen-workspace-evidence.md)
- [Run B explanation](docs/run-b-cortrix-plugin.md)
- [Run A manual Runbook](docs/run-a-frozen-workspace-evidence-step-by-step.md)
- [Run B manual Runbook](docs/run-b-cortrix-plugin-step-by-step.md)

Agent discovery begins at the repository root with `agent.json`, then `./democtl describe --scenario api-version-drift-coding-agent --json` and `./democtl validate --scenario api-version-drift-coding-agent`. Those safe commands make no external calls. Live execution remains a separately authorized path.

When the accepted-run pointer reports `accepted`, start the read-only evidence page with `make viewer-harness SCENARIO=api-version-drift-coding-agent`. The viewer refuses candidate evidence and renders only the independently reviewed identity chain.

The intended result is narrow: Run A exposes why stale workspace evidence can preserve the removed `retries=3` example, while Run B should retrieve the current `RetryPolicy`, the deprecation notice, the migration guide, and maintained contract tests. The application resolver, not Cortrix or the model, owns authority and permits explanation plus isolated test planning only.
