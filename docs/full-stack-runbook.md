# Full Stack runbook

This is a manual, cost-bearing workflow. The runner fails closed and does not use a local generative LLM.

For the scenario-specific interpretation of each path, read [Run A: PostgreSQL and pgvector](../scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector.md) and [Run B: Cortrix Full Stack](../scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack.md). The live command intentionally produces both paths as one evidence-bound candidate. The separate [Run A manual Runbook](../scenarios/order-api-field-migration/docs/run-a-postgresql-pgvector-step-by-step.md) and [Run B manual Runbook](../scenarios/order-api-field-migration/docs/run-b-cortrix-full-stack-step-by-step.md) expose the underlying Docker, HTTP, Python, and SQL operations for human learning; those direct commands do not create official candidate evidence.

## 1. Obtain the pinned Cortrix source and prepare the image

The reviewed distribution method is a local source build. This repository does not publish or pull `cortrix-demo:32b82f6` from a registry. The machine-readable contract is [`runtime/image-provenance.json`](../runtime/image-provenance.json).

From the `cortrix-demos` repository root, obtain the public Cortrix source and detach it at the required revision:

```bash
mkdir -p .runtime
git clone https://github.com/cortrix/cortrix.git .runtime/cortrix-src
git -C .runtime/cortrix-src checkout --detach 32b82f6f8f1d7a41349f408969ff03b7997b6c15
test "$(git -C .runtime/cortrix-src rev-parse HEAD)" = "32b82f6f8f1d7a41349f408969ff03b7997b6c15"
```

If the ignored checkout already exists, do not clone over it. Fetch the required commit from its configured origin, check it out in detached mode, and run the same exact revision test.

Prepare the image before preflight or live execution:

```bash
./democtl prepare-image \
  --scenario order-api-field-migration \
  --cortrix-source .runtime/cortrix-src
```

The command verifies the source checkout, Docker engine, Compose installation, image name, and required `org.opencontainers.image.revision` label. It reports `action: reused` when the matching local image exists and `action: built` only when it must build from `deploy/Dockerfile`. It makes zero external model calls and does not download BGE models.

The first build compiles the Cortrix C++ service and should be planned in minutes rather than seconds; actual time depends on CPU, Docker cache, and network state. The validated pinned image is approximately 149 MiB, while source build cache and the approximately 1.2 GB BGE model assets require additional disk space. Plan several gigabytes of free Docker storage and enough memory for the Cortrix build and live services. A replay-only validation does not require this build.

The source checkout is ignored. Its local path is never written to curated evidence.

## 2. Record current official pricing

Immediately before a live run, read the official [DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing) and record the observed values without manually editing JSON:

```bash
./democtl record-pricing \
  --input-cache-hit 0.0028 \
  --input-cache-miss 0.14 \
  --output-price 0.28
```

The values above were observed for `DeepSeek-V4-Flash` on 2026-08-04. Recheck the official page and replace all three values when running later.

The direct Full Stack runner computes a conservative cumulative-attempt cost bound from the current prices and caps new authorized direct execution at USD 1.00. Harness campaigns use the budget in their selected campaign contract, with a runner guard of USD 5.00 per campaign. The repository-supplied next-evidence contracts use USD 0.30 for foundation and USD 0.60 for operational continuity. Those values describe the maintainer-reviewed evidence run, not a universal limit on an operator's separate campaign. A price change never expands the selected contract, and historical accepted evidence retains its original budget as immutable run identity.

## 3. Inject the secret and run

The runner resolves the required secret in this order:

1. `DEEPSEEK_API_KEY` in the process environment.
2. An absolute profile path selected by `CORTRIX_LLM_SECRET_FILE`.
3. `${XDG_CONFIG_HOME:-$HOME/.config}/cortrix/secrets/llm/current.yaml`.

The default profile is a local workstation convention, not a repository file. On POSIX systems, its resolved target must be owned by the current user with no group or other permissions. A profile must contain exactly one top-level `api_key` and `base_url`, and every declared role model must match `deepseek-v4-flash`. The DeepSeek endpoint may omit the trailing `/v1` used by the runtime adapter.

For a reusable local default, keep the filled profile outside every Git checkout and point `current.yaml` to it:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/cortrix/secrets/llm"
ln -sfn deepseek-v4-flash.yaml "${XDG_CONFIG_HOME:-$HOME/.config}/cortrix/secrets/llm/current.yaml"
chmod 700 "${XDG_CONFIG_HOME:-$HOME/.config}/cortrix/secrets/llm"
chmod 600 "${XDG_CONFIG_HOME:-$HOME/.config}/cortrix/secrets/llm/deepseek-v4-flash.yaml"
```

Do not export the real key from a shell startup file or a parent workspace `.envrc`. The runner reads a profile only after an explicitly authorized, cost-bearing command reaches preflight. It records only `secret_source: environment`, `explicit_profile`, or `default_profile`; it never records the profile path or value.

The canonical `main` branch is always eligible for a live candidate. A declared presentation localization branch may also run a local validation candidate when `localization-base.yaml` binds it to an ancestor on `main` and every changed file stays inside the presentation-only allowlist. This exception does not allow a localized branch to stage or replace accepted evidence; curation remains restricted to `main`.

The guided mode exposes both comparison paths in their natural order:

```bash
./democtl walkthrough init --reviewed-attempt-limit 2
./democtl walkthrough run-a
./democtl walkthrough inspect --component run-a
./democtl walkthrough run-b
./democtl walkthrough inspect --component run-b
./democtl walkthrough finalize
./democtl walkthrough inspect --component candidate
```

`make full-stack` remains the supported non-interactive equivalent when staged observation is unnecessary.

The runner allows one direct provider contract smoke and one complete candidate run per attempt. It may start a second attempt only after an HTTP 429, HTTP 5xx, or timeout, and the retry receives a new run ID. A deterministic assertion or identity failure never retries.

The default reviewed attempt limit is two. The sealed 2.x scenario campaign has a hard cap of four slots. An explicit review may authorize the exact four-slot campaign only when its conservative bound remains within the current USD 1.00 repository policy:

```bash
./democtl run-full-stack --reviewed-attempt-limit 4
```

The runner preserves the legacy attempt ledger and writes 2.x slots to an isolated campaign ledger. A transient retry consumes another slot. A deterministic failure cannot rerun the same sealed scenario version, and the campaign cannot start a fifth slot.

The ingestion gate derives its expected chunk count from the durable text blocks produced for the frozen fixtures. It requires F03, F35, F38, and the final enrichment state for every actual block, plus F41 summaries for every fixture document. It does not reuse a fixed chunk count from a different source demo.

The runner reapplies the tracked idempotent PostgreSQL schema after the database becomes ready. This is required because the official PostgreSQL image executes `/docker-entrypoint-initdb.d` only when it initializes a new empty volume; a reused local demo volume must not depend on that one-time behavior.

The scenario contract sends both Run B queries with `granularity=chunk` and requests four final candidates. The response must echo the granularity in `explain.granularity`, retrieve both version-conflict documents, and expose finite BGE rerank scores. F41 summaries remain mandatory ingestion evidence, but this scenario does not include document-level discovery candidates in the BGE cross-encoder ranking.

## 4. Inspect the candidate

Candidate evidence is written under ignored `.runs/<run_id>/`. A successful candidate includes Run A, Run B, two serialized query records, durable identity, resolver output, model checksums, runtime identity, a cleanup receipt, a pricing snapshot, partial usage visibility, and a candidate manifest.

The pricing snapshot is a timestamped transcription from the official provider page, not an automated freshness proof. Partial usage is acceptable only as an explicitly disclosed limitation: the conservative reviewed budget contract must pass, `estimated_total_usd` remains unknown, and no public total cost claim is allowed.

The candidate is not screenshot-eligible. An authorized reviewer may inspect it in a real browser with `make viewer-candidate-qa RUN_ID=<run_id>`, but that separate local route is prominently labeled as Candidate QA and cannot be registered as accepted screenshot evidence. Human review must accept the candidate before curated evidence can be staged for the accepted viewer. No public cost claim is allowed when usage visibility is partial.

## 5. Cleanup contract

The runner removes only the three namespaces derived from its run ID, stops the dedicated Compose services, releases the three loopback listeners, and removes the ignored runtime config that held the injected secret. It preserves Docker volumes and the downloaded BGE model cache to avoid unrelated or expensive deletion.
