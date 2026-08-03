# Cortrix Demos Contributor Instructions

This repository contains reproducible, evidence-backed demos for Cortrix.

## Public Surface

- Treat every tracked file as future-public material, even while the repository is private.
- Use American English for code, comments, tests, CLI output, fixtures, documentation, and user-visible text.
- Do not add private workspace links, local absolute paths, internal reviews, raw private logs, runtime caches, or credentials.
- Do not copy files or Git history from legacy demo repositories. New material must have recorded provenance.

## Evidence

- A run advances through `created -> running -> candidate -> accepted | rejected`.
- Automation may produce a candidate or rejected run. Only a recorded SecondScott Clean Room `PASS` may promote a candidate to accepted; final Human Review follows screenshot capture.
- Screenshots must come from the read-only viewer rendering one accepted run. Do not synthesize or manually rewrite result images.
- Preserve source revision, release identity, fixture and model checksums, provider/model identity, resolver output, cleanup receipts, and cost visibility.
- Reject a run when a required path is missing, degraded, locally substituted, over budget, or not attributable to a durable source identity.

## Secrets and External Calls

- Read `DEEPSEEK_API_KEY` only from the process environment.
- Never print or persist the key in tracked files, evidence, logs, screenshots, command examples, or Git history.
- Do not use a local generative-model fallback.
- External Full Stack execution is manual and cost-gated. Pull requests must not call external model APIs.

## Repository Boundaries

- Do not add a `LICENSE` file until provenance review and a separate license decision are complete.
- Do not add GitHub Actions workflows, Pages configuration, releases, forks, or remote localization branches without a separate human gate.
- Local `zh-CN` work is presentation-only unless a separate run is approved. It must not alter fixtures, queries, prompts, raw evidence, scores, source IDs, traces, or checksums.
- Remote repository creation and every push require the explicit authorization defined by the active work package.

## Verification

- Run `make validate` before committing.
- Run the public-safety scan against the full tracked tree and staged diff.
- Keep `main` as the canonical English branch.
