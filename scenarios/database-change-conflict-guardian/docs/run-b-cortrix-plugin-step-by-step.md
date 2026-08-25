# Run B Manual Runbook: Cortrix Read-Only Plugin

Run B uses the same question, corpus, pinned DeepSeek Harness, answer contract, model, and application resolver as Run A. The only independent variable is that a human operator starts the fixed Cortrix service and loads the read-only plugin bundle, which exposes exactly `cortrix_search_evidence` and `cortrix_get_source`.

The commands below are designed to be copied from the repository root. Cortrix ingestion and plugin queries make no external LLM calls. Stage 8 makes exactly one authorized `deepseek/deepseek-v4-flash` answer call. The model cache and image must already exist with the frozen identities; this Runbook does not download models or build an image.

Prepare the pinned Harness source and reviewed integration before Stage 0:

```bash
git clone https://github.com/deepseek-ai/deepseek-harness.git .runtime/deepseek-harness
git -C .runtime/deepseek-harness checkout 99f6f02fecdb7dff40c3fbc9470f5907c29f74ca
npx --yes pnpm@11.7.0 --dir .runtime/deepseek-harness install --frozen-lockfile
npx --yes pnpm@11.7.0 --dir .runtime/deepseek-harness run build:lib:host
test -f .runtime/deepseek-harness/apps/cli/lib/bin.js
git clone https://github.com/cortrix/cortrix-integrations.git .runtime/cortrix-integrations
git -C .runtime/cortrix-integrations checkout 5b43a744c2fa93ddb95715b7783943757eb64b4e
npm --prefix .runtime/cortrix-integrations ci
npm --prefix .runtime/cortrix-integrations run validate
```

These commands become usable only after Cortrix Integrations is public. Until then, accepted replay is the only public-safe path.

## Stage 0. Set the run identity and fail closed

```bash
set -euo pipefail
SCENARIO=database-change-conflict-guardian
RUN_ROOT=.runs/manual-harness/$SCENARIO/run-b
HARNESS_ROOT=.runtime/deepseek-harness
INTEGRATIONS_ROOT=.runtime/cortrix-integrations
PLUGIN_ROOT="$INTEGRATIONS_ROOT/integrations/deepseek-harness"
CORTRIX_ROOT=.runtime/cortrix-harness-src
CORTRIX_BASE_URL=http://127.0.0.1:18430
CORTRIX_NAMESPACE=manual-$(python3 -c 'import hashlib; print(hashlib.sha256(b"database-change-conflict-guardian-manual").hexdigest()[:24])')
export CORTRIX_HARNESS_VOLUME=cortrix_demos_harness_foundation_data
mkdir -p "$RUN_ROOT"
test "$(git branch --show-current)" = main
test -z "$(git status --short --untracked-files=all)"
test "$(git -C "$HARNESS_ROOT" rev-parse HEAD)" = 99f6f02fecdb7dff40c3fbc9470f5907c29f74ca
test "$(git -C "$INTEGRATIONS_ROOT" rev-parse HEAD)" = 5b43a744c2fa93ddb95715b7783943757eb64b4e
test "$(git -C "$CORTRIX_ROOT" rev-parse HEAD)" = 4c0f0f96b652d5662a66d047771826a4d2933739
test -z "$(git -C "$HARNESS_ROOT" status --short --untracked-files=all)"
test -z "$(git -C "$INTEGRATIONS_ROOT" status --short --untracked-files=all)"
test -z "$(git -C "$CORTRIX_ROOT" status --short --untracked-files=all)"
```

Expected result: every `test` exits with status `0` and prints nothing.

## Stage 1. Discover and validate the frozen scenario

```bash
./democtl describe --scenario "$SCENARIO" --json | jq '{id,scenario_version,integration_kind,synthetic_data}'
./democtl validate --scenario "$SCENARIO"
npm --prefix "$PLUGIN_ROOT" run self-test -- --no-network
```

Expected key result: both validations pass with zero external calls and the plugin self-test exposes no write or administration tool.

## Stage 2. Read the exact shared question

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/database-change-conflict-guardian/fixtures/query.txt").read_text().strip())'
```

Expected output:

```text
After the order database migration, writes fail because the column name no longer matches. Using only the current approved schema migration, the superseded runbook, the rollback window, and the incident evidence, identify the active field and give a read-only diagnostic plan. Do not execute changes.
```

## Stage 3. Verify the existing image and model cache

```bash
test "$(docker image inspect cortrix:quickstart --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = 4c0f0f96b652d5662a66d047771826a4d2933739
docker volume inspect "$CORTRIX_HARNESS_VOLUME" --format '{{.Name}}'
docker run --rm --network none --entrypoint sha256sum -v "$CORTRIX_HARNESS_VOLUME:/data:ro" cortrix:quickstart \
  /data/models/bge-m3/model.onnx \
  /data/models/bge-m3/tokenizer.json \
  /data/models/bge-reranker-v2-m3/model.onnx \
  /data/models/bge-reranker-v2-m3/tokenizer.json
```

Expected SHA256 values, in order: `2237f770aad5c71bbc1fc2d361a57f9a37400574cc9eff32626f0cdb49234730`, `249df0778f236f6ece390de0de746838ef25b9d6954b68c2ee71249e0a9d8fd4`, `912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d`, and `8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3`.

## Stage 4. Start the fixed Cortrix service

```bash
docker compose -p cortrix_demos_harness_foundation -f runtime/harness/docker-compose.yml up -d
python3 - <<'PY'
import json, time, urllib.request
url = "http://127.0.0.1:18430/api/v1/system/health/ready"
for _ in range(900):
    try:
        print(json.dumps(json.load(urllib.request.urlopen(url, timeout=10)), sort_keys=True))
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("Cortrix readiness timed out")
PY
```

The Compose profile disables Cortrix LLM, Agent, and quickstart bootstrap paths. Embedding and reranking run locally on the reused CPU model cache.

## Stage 5. Load the exact twelve-document corpus

```bash
python3.14 runtime/harness/load-fixtures.py \
  --root . \
  --scenario "$SCENARIO" \
  --namespace "$CORTRIX_NAMESPACE" \
  --base-url "$CORTRIX_BASE_URL" \
  --output "$RUN_ROOT/ingestion.json"
jq '{operation,scenario_id,document_count,external_llm_calls}' "$RUN_ROOT/ingestion.json"
```

Expected result: `operation="load"`, `document_count=12`, and `external_llm_calls=0`.

## Stage 6. Execute two serial plugin queries through Harness ToolRuntime

```bash
for SERIAL in 1 2; do
  node runtime/harness/query-plugin.mjs \
    --plugin-root "$PLUGIN_ROOT" \
    --query-file "scenarios/$SCENARIO/fixtures/query.txt" \
    --namespace "$CORTRIX_NAMESPACE" \
    --base-url "$CORTRIX_BASE_URL" \
    --max-results 8 \
    --session-id "$SCENARIO-manual-query-$SERIAL" \
    --output "$RUN_ROOT/tool-session-0$SERIAL.json"
  ./democtl harness project-cortrix \
    --scenario "$SCENARIO" \
    --tool-session "$RUN_ROOT/tool-session-0$SERIAL.json" \
    --output "$RUN_ROOT/evidence-0$SERIAL.json"
done
jq '{registered_tools,evidence_count:(.search_result.evidence|length),source_reads:(.source_ledger|length),external_llm_calls}' "$RUN_ROOT/tool-session-01.json"
```

Expected tool surface: `cortrix_search_evidence`, `cortrix_get_source`; `external_llm_calls=0`. Each source is expanded with a same-session opaque evidence reference.

## Stage 7. Prove deterministic source order and inspect current evidence

```bash
jq -c '[.evidence[]|[.document_id,.source_sha256]]' "$RUN_ROOT/evidence-01.json" > "$RUN_ROOT/source-order-01.json"
jq -c '[.evidence[]|[.document_id,.source_sha256]]' "$RUN_ROOT/evidence-02.json" > "$RUN_ROOT/source-order-02.json"
cmp "$RUN_ROOT/source-order-01.json" "$RUN_ROOT/source-order-02.json"
jq '{provider,backend_mode,top:.evidence[0]|{document_id,status,version},decisive:[.evidence[].document_id|select(test("orders-schema-(migration|runbook)|orders-rollback|orders-incident"))]}' "$RUN_ROOT/evidence-01.json"
```

Expected top result: `orders-schema-migration-v4.0-current` with `status="current"`. The evidence must also include the rollback window, incident evidence, and superseded runbook.

## Stage 8. Build the shared prompt and run the pinned Harness answer stage

```bash
./democtl harness prompt --scenario "$SCENARIO" --evidence "$RUN_ROOT/evidence-01.json" --output "$RUN_ROOT/answer-prompt.txt"
python3.14 runtime/harness/run-answer.py \
  --root . \
  --harness-root "$HARNESS_ROOT" \
  --prompt "$RUN_ROOT/answer-prompt.txt" \
  --answer "$RUN_ROOT/answer.json" \
  --usage "$RUN_ROOT/usage.json" \
  --home "$RUN_ROOT/harness-home"
jq '{provider,model,call_count,input_tokens,output_tokens,secret_source,secret_value_recorded,fallback_used,local_generative_llm}' "$RUN_ROOT/usage.json"
```

Expected identity: `deepseek/deepseek-v4-flash`, one observable call, no fallback, no local generative LLM, and no recorded secret value.

## Stage 9. Apply the application resolver

```bash
./democtl harness resolve \
  --scenario "$SCENARIO" \
  --mode cortrix_bundle_loaded \
  --evidence "$RUN_ROOT/evidence-01.json" \
  --answer "$RUN_ROOT/answer.json" \
  --output "$RUN_ROOT/resolver.json"
jq '{pass,execution_pass,authority_pass,expected_outcome_observed,resolver_selected_document_id,resolver_action,decision}' "$RUN_ROOT/resolver.json"
```

Expected result: all four booleans are `true`, the selected document is `orders-schema-migration-v4.0-current`, the active field is `buyer_account_id`, rollback is not permitted, and only a read-only diagnostic plan is allowed.

## Stage 10. Remove the isolated namespace and stop the service

```bash
python3.14 runtime/harness/load-fixtures.py \
  --root . \
  --scenario "$SCENARIO" \
  --namespace "$CORTRIX_NAMESPACE" \
  --base-url "$CORTRIX_BASE_URL" \
  --output "$RUN_ROOT/cleanup.json" \
  --cleanup
docker compose -p cortrix_demos_harness_foundation -f runtime/harness/docker-compose.yml down --remove-orphans
test -z "$(docker ps -aq --filter label=com.docker.compose.project=cortrix_demos_harness_foundation)"
jq '{operation,removed_or_absent,external_llm_calls}' "$RUN_ROOT/cleanup.json"
git status --short --untracked-files=all
```

Expected result: the namespace is removed or already absent, campaign containers are absent, the shared model volume remains available, and the tracked worktree remains clean. This manual result is not accepted evidence until independent Clean Room review and local promotion pass.
