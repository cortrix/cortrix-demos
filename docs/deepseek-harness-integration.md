# DeepSeek Harness Integration

Cortrix Demos uses the Preview `@cortrix/dsh-cortrix` integration to give the pinned DeepSeek Harness two explicit, read-only evidence tools:

- `cortrix_search_evidence`
- `cortrix_get_source`

The integration source belongs to [Cortrix Integrations](https://github.com/cortrix/cortrix-integrations), not this repository. Cortrix Demos owns the scenarios, comparison runner, application resolvers, accepted evidence, and viewer.

## Fixed compatibility

| Component | Reviewed identity |
| --- | --- |
| Cortrix integration | `@cortrix/dsh-cortrix` `0.1.0`, Preview |
| DeepSeek Harness | commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`, package family `0.1.0-rc.7` |
| Cordis | `4.0.1` |
| Cortrix query API | commit `4c0f0f96b652d5662a66d047771826a4d2933739` |
| Answer model | `deepseek/deepseek-v4-flash` |

The local release candidate currently pins Cortrix Integrations commit `0b31efc5663cd5d458a681f423abc434048bd559`. A source change invalidates this candidate and requires another review.

This is a fixed compatibility result, not a claim about later Harness, Cordis, Cortrix, or model versions.

## Prepare the pinned Harness source

The live campaign requires the exact Harness checkout and its Host build. These commands use the package manager version declared by Harness and do not require a language model key:

```bash
git clone https://github.com/deepseek-ai/deepseek-harness.git .runtime/deepseek-harness
git -C .runtime/deepseek-harness checkout 99f6f02fecdb7dff40c3fbc9470f5907c29f74ca
npx --yes pnpm@11.7.0 --dir .runtime/deepseek-harness install --frozen-lockfile
npx --yes pnpm@11.7.0 --dir .runtime/deepseek-harness run build:lib:host
test -f .runtime/deepseek-harness/apps/cli/lib/bin.js
test -z "$(git -C .runtime/deepseek-harness status --short --untracked-files=all)"
```

## Prepare the integration

The Cortrix Integrations repository is not public yet. The commands below become valid only after that repository is publicly available at the exact reviewed commit already shown.

```bash
git clone https://github.com/cortrix/cortrix-integrations.git .runtime/cortrix-integrations
git -C .runtime/cortrix-integrations checkout 0b31efc5663cd5d458a681f423abc434048bd559
npm --prefix .runtime/cortrix-integrations ci
npm --prefix .runtime/cortrix-integrations run validate
```

The integration path used by the campaign is:

```text
.runtime/cortrix-integrations/integrations/deepseek-harness
```

Do not substitute an unreviewed branch, package version, or local copy. A source change invalidates compatibility and any accepted run that binds a different integration commit.

## Responsibility boundary

DeepSeek Harness owns the Agent loop, tool execution, and durable session events. The integration validates trusted configuration, calls the fixed Cortrix query API, projects bounded evidence, and reconstructs same-session source references. Cortrix owns indexing and retrieval. The demo application independently decides whether a source is current and what action is allowed.

The integration does not upload data, write memory, edit code, run a shell, execute remediation, choose a namespace, or replace application authorization.

## Safe verification

Accepted replay and archive verification make no external calls:

```bash
./democtl harness verify-accepted --scenario database-change-conflict-guardian
./democtl harness verify-accepted --scenario api-version-drift-coding-agent
./democtl harness verify-accepted --scenario payment-incident-shift-handoff
./democtl harness verify-accepted --scenario migration-decision-recovery
```

A new live campaign is a separate authorization boundary. It requires public dependency preparation, a dated pricing snapshot, an approved budget, the protected provider credential, and a new independent Clean Room review.
