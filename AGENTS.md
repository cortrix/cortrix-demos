# Cortrix Demos Contributor Instructions

This repository contains reproducible, evidence-backed demos for Cortrix.

## Agent Bootstrap

If this is your first interaction with the repository, read `agent.json` and follow its `bootstrap.safe_default` commands in order:

```bash
./democtl list --json
./democtl describe --scenario order-api-field-migration --json
./democtl validate --scenario order-api-field-migration
./democtl verify-accepted
```

These commands are read-only, make no external model calls, and locate the accepted evidence without private workspace knowledge. Treat accepted replay as the default operating mode.

Do not run `preflight`, `run-full-stack`, `stage-accepted`, `record-screenshot`, or any remote Git action unless the current task explicitly authorizes that boundary. A live Full Stack run is cost-bearing and produces a candidate, never automatically accepted evidence.

## Public Surface

- Treat every tracked file as future-public material, even while the repository is private.
- Use American English for code, comments, tests, CLI output, fixtures, documentation, and user-visible text.
- Do not add private workspace links, local absolute paths, internal reviews, raw private logs, runtime caches, or credentials.
- Do not copy files or Git history from legacy demo repositories. New material must have recorded provenance.
- For any pull request, issue, discussion, review, comment, status change, or other public action in a public repository under `github.com/cortrix`, use only content, facts, evidence, links, and reasons that are publicly visible in the target repository and independently verifiable from that repository alone.
- Private repositories, local private files, internal memory, and unpublished communication may be used only as private search leads. Their information must be independently reproduced and verified in the target public repository before it can support a public action. Never expose or allude to internal identifiers, task or feature IDs, decision states, document paths, tracking labels, unpublished facts, or conclusions supported only by private material.
- If a conclusion, request, or action cannot be supported solely by public evidence in the target repository, do not publish it or use it as the basis for a public action. Public responses should describe only observable problems, impact, reproduction evidence, and required changes.

## Evidence

- A run advances through `created -> running -> candidate -> accepted | rejected`.
- Automation may produce a candidate or rejected run. Only a recorded SecondScott Clean Room `PASS` may promote a candidate to accepted; final Human Review follows screenshot capture.
- Screenshots must come from the read-only viewer rendering one accepted run. Do not synthesize or manually rewrite result images.
- Preserve source revision, release identity, fixture and model checksums, provider/model identity, resolver output, cleanup receipts, and cost visibility.
- Reject a run when a required path is missing, degraded, locally substituted, over budget, or not attributable to a durable source identity.

## Secrets and External Calls

- Read only the secret environment variable named by the selected implemented provider profile. The current scenario uses `DEEPSEEK_API_KEY`.
- Never print or persist the key in tracked files, evidence, logs, screenshots, command examples, or Git history.
- Do not use a local generative-model fallback.
- External Full Stack execution is manual and cost-gated. Pull requests must not call external model APIs.

## Repository Boundaries

- All repository-owned code, documentation, fixtures, schemas, and visual assets are Apache-2.0. Preserve `LICENSE`, `NOTICE`, provenance, and trademark boundaries.
- Do not add GitHub Actions workflows, Pages configuration, releases, forks, or remote localization branches without a separate human gate.
- Local `zh-CN` work is presentation-only unless a separate run is approved. It must not alter fixtures, queries, prompts, raw evidence, scores, source IDs, traces, or checksums.
- Remote repository creation and every push require the explicit authorization defined by the active work package.

## Verification

- Run `make validate` before committing.
- Verify that `agent.json`, `scenarios/registry.json`, and each scenario's technology profile remain mutually discoverable.
- Run the public-safety scan against the full tracked tree and staged diff.
- Keep `main` as the canonical English branch.
