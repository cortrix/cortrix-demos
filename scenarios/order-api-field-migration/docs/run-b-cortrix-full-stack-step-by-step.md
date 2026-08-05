# Run B Manual Runbook: Cortrix Full Stack

This Runbook reproduces Run B with direct Docker, HTTP, Python, and evidence-inspection commands. It does not use `democtl` to execute the path.

Run B is cost-bearing. It uses the pinned Cortrix image, BGE-M3 embeddings, BM25/FTS5, contextualized retrieval, HyPE, sparse retrieval, RRF, the BGE cross-encoder, DeepSeek query fusion, DeepSeek listwise reranking, and an application lifecycle resolver. Do not begin unless the external call, secret, and cost boundary is authorized.

This manual path bypasses the Agent runner's attempt ledger, cumulative budget guard, evidence manifest, and automatic rejection state. Use it only as an authorized educational reproduction. Its output is not official candidate or accepted evidence; use the repository's Agent workflow when evidence identity is required.

The output excerpts come from accepted run `order-api-field-migration-20260804T085505Z`. Namespace, task, document, and child IDs vary by run. The frozen document identities, ranking layers, resolver decision, and required checks must match.

## 1. Confirm the shared contract

Run all commands from the repository root. Confirm that Run B receives the exact same question as Run A:

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/order-api-field-migration/fixtures/query.txt").read_text().strip())'
```

Expected output:

```text
Create order now rejects a payload with account_id as an unknown field. Which request field should replace it?
```

Confirm the frozen input checksums before any external call:

```bash
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path("scenarios/order-api-field-migration/fixtures")
manifest = json.loads((root / "manifest.json").read_text())
items = [manifest["query"], *manifest["documents"]]
for item in items:
    actual = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
    assert actual == item["sha256"], item["path"]
print({"documents": len(manifest["documents"]), "checksums": "pass"})
PY
```

## 2. Prepare the pinned runtime

Prepare the same pinned image used by Run A if it is not already present:

```bash
set -euo pipefail
mkdir -p .runtime
if [ ! -d .runtime/cortrix-src/.git ]; then
  git clone https://github.com/cortrix/cortrix.git .runtime/cortrix-src
fi
git -C .runtime/cortrix-src checkout --detach 32b82f6f8f1d7a41349f408969ff03b7997b6c15
SOURCE_HEAD="$(git -C .runtime/cortrix-src rev-parse HEAD)"
if [ "$SOURCE_HEAD" != "32b82f6f8f1d7a41349f408969ff03b7997b6c15" ]; then
  printf 'source revision mismatch: %s\n' "$SOURCE_HEAD" >&2
  exit 1
fi
if ! docker image inspect cortrix-demo:32b82f6 >/dev/null 2>&1; then
  docker build \
    --tag cortrix-demo:32b82f6 \
    --file .runtime/cortrix-src/deploy/Dockerfile \
    --build-arg CORTRIX_SOURCE_REVISION=32b82f6f8f1d7a41349f408969ff03b7997b6c15 \
    .runtime/cortrix-src
fi
IMAGE_REVISION="$(docker image inspect cortrix-demo:32b82f6 --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
if [ "$IMAGE_REVISION" != "32b82f6f8f1d7a41349f408969ff03b7997b6c15" ]; then
  printf 'image source revision mismatch: %s\n' "$IMAGE_REVISION" >&2
  exit 1
fi
printf 'image source revision: %s\n' "$IMAGE_REVISION"
```

Immediately before the run, open the official [DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing). Replace the three example values below if the page has changed, then execute the local one-attempt budget gate. A price change never expands the repository's `USD 1.00` ceiling:

```bash
export DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M="0.0028"
export DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M="0.14"
export DEEPSEEK_OUTPUT_USD_PER_M="0.28"
mkdir -p .runs/manual-cortrix
python3 - <<'PY'
import datetime
import json
import math
import os
from pathlib import Path

policy = json.loads(Path("config/external-call-policy.json").read_text())
profile = json.loads(Path("scenarios/order-api-field-migration/profiles/full-stack.json").read_text())
prices = {
    "input_cache_hit": float(os.environ["DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M"]),
    "input_cache_miss": float(os.environ["DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M"]),
    "output": float(os.environ["DEEPSEEK_OUTPUT_USD_PER_M"]),
}
if any(not math.isfinite(value) or value < 0 for value in prices.values()):
    raise RuntimeError("Pricing values must be finite and non-negative")
budget_usd = float(policy["budget_usd"])
guard = profile["budget_guard"]
attempt_limit = 1
if not math.isfinite(budget_usd) or budget_usd <= 0:
    raise RuntimeError("Budget must be finite and positive")
bound_usd = round(
    attempt_limit
    * (
        int(guard["maximum_input_tokens"]) * prices["input_cache_miss"]
        + int(guard["maximum_output_tokens"]) * prices["output"]
    )
    / 1_000_000,
    8,
)
if budget_usd != 1.0 or bound_usd > budget_usd:
    raise RuntimeError({"budget_usd": budget_usd, "conservative_bound_usd": bound_usd})
snapshot = {
    "schema_version": 1,
    "observed_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "official_url": "https://api-docs.deepseek.com/quick_start/pricing",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "currency": "USD",
    "unit": "per_million_tokens",
    "prices_per_million_tokens": prices,
    "attempt_limit": attempt_limit,
    "budget_usd": budget_usd,
    "conservative_bound_usd": bound_usd,
}
Path(".runs/manual-cortrix/pricing-snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
print({"budget_usd": budget_usd, "attempt_limit": attempt_limit, "conservative_bound_usd": bound_usd, "pass": True})
PY
```

With the reference prices above, the expected bound is:

```text
{'budget_usd': 1.0, 'attempt_limit': 1, 'conservative_bound_usd': 0.042, 'pass': True}
```

Stop if the gate fails. This manual session permits one complete attempt only; do not retry a deterministic failure.

Inject the secret through the current shell or a secret manager. Confirm only that it exists; never print its value:

```bash
test -n "${DEEPSEEK_API_KEY:-}" && echo "DEEPSEEK_API_KEY is set"
```

Materialize a mode-`0600` runtime configuration by replacing the three tracked placeholders from the process environment:

```bash
mkdir -p .runtime/config .runs/manual-cortrix
python3 - <<'PY'
import os
from pathlib import Path

key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
if len(key) < 20:
    raise RuntimeError("DEEPSEEK_API_KEY is missing")
source = Path("runtime/config/cortrix.full-stack.yaml").read_text()
placeholder = "__RUNTIME_API_KEY__"
if source.count(placeholder) != 3:
    raise RuntimeError("Expected exactly three API key placeholders")
target = Path(".runtime/config/cortrix.yaml")
target.write_text(source.replace(placeholder, key))
target.chmod(0o600)
print({"config": ".runtime/config/cortrix.yaml", "mode": "0600", "secret_printed": False})
PY
```

Export the environment consumed by Docker Compose:

```bash
export CORTRIX_LLM_ENABLED=true
export CORTRIX_LLM_PROVIDER=deepseek
export CORTRIX_LLM_API_KEY="$DEEPSEEK_API_KEY"
export CORTRIX_LLM_MODEL=deepseek-v4-flash
export CORTRIX_LLM_BASE_URL=https://api.deepseek.com/v1
B_NS="order-b-manual-$(date -u +%Y%m%dT%H%M%SZ | tr '[:upper:]' '[:lower:]')"
export B_NS
printf 'B_NS=%s\n' "$B_NS"
```

## 3. Start the services

Start PostgreSQL and force-recreate Cortrix with the Full Stack configuration:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml up -d postgres
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml up -d --force-recreate cortrix
```

Wait for the API and metrics endpoints independently, then save the metrics baseline before ingestion. API readiness does not guarantee that the separate metrics listener is already returning complete responses. The pinned Cortrix metrics server intentionally listens on loopback inside the Cortrix container, so read it with `docker-compose exec` rather than through a host port:

```bash
until curl -fsS http://127.0.0.1:18420/api/v1/system/health/ready >/dev/null; do sleep 2; done
METRICS_READY=0
for _ in $(seq 1 60); do
  if docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix curl -fsS --max-time 10 http://127.0.0.1:9091/metrics > .runs/manual-cortrix/metrics-before-ingest.prom.tmp; then
    METRICS_READY=1
    break
  fi
  sleep 2
done
test "$METRICS_READY" = 1
mv .runs/manual-cortrix/metrics-before-ingest.prom.tmp .runs/manual-cortrix/metrics-before-ingest.prom
```

Verify the loaded model files directly inside the container against the frozen checksums:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix sh -c '
printf "%s  %s\n" \
  2237f770aad5c71bbc1fc2d361a57f9a37400574cc9eff32626f0cdb49234730 /data/models/bge-m3/model.onnx \
  249df0778f236f6ece390de0de746838ef25b9d6954b68c2ee71249e0a9d8fd4 /data/models/bge-m3/tokenizer.json \
  912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d /data/models/bge-reranker-v2-m3/model.onnx \
  8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3 /data/models/bge-reranker-v2-m3/tokenizer.json \
  | sha256sum -c -
'
```

Every line must end in `OK`. The values come from `runtime/model-manifest.json`; `sha256sum` exits nonzero and stops the run on any mismatch.

## 4. Load the comparison data

Create one namespace, upload the four fixture documents, and wait for every asynchronous ingestion task. These are direct Cortrix HTTP API calls:

```bash
python3 - <<'PY'
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

base = "http://127.0.0.1:18420/api/v1"
namespace = os.environ["B_NS"]
fixture_root = Path("scenarios/order-api-field-migration/fixtures")
manifest = json.loads((fixture_root / "manifest.json").read_text())

def call(method, path, payload=None, expected=(200,)):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            status = response.status
            value = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        status = error.code
        value = json.loads(error.read().decode() or "{}")
    if status not in expected:
        raise RuntimeError({"status": status, "response": value})
    return status, value

status, _ = call("GET", "/namespaces/" + urllib.parse.quote(namespace), expected=(200, 404))
if status == 404:
    call("POST", "/namespaces", {"name": namespace, "display_name": namespace}, expected=(201,))

for item in manifest["documents"]:
    metadata = {key: value for key, value in item.items() if key != "sha256"}
    metadata.update({"manual_run": True, "fixture_sha256": item["sha256"]})
    _, accepted = call(
        "POST",
        "/documents",
        {
            "namespace": namespace,
            "filename": item["path"],
            "content": (fixture_root / item["path"]).read_text(),
            "metadata": metadata,
        },
        expected=(202,),
    )
    task_id = accepted["task_id"]
    for _ in range(900):
        _, progress = call("GET", "/documents/tasks/" + urllib.parse.quote(task_id) + "/progress")
        state = str(progress.get("status", "")).lower()
        if state in {"ready", "completed", "success", "succeeded"}:
            if progress.get("error_code") or progress.get("error_msg"):
                raise RuntimeError(progress)
            print({"document": item["document_id"], "status": state})
            break
        if state in {"failed", "cancelled", "canceled", "error"}:
            raise RuntimeError(progress)
        time.sleep(1)
    else:
        raise TimeoutError(task_id)
PY
```

Wait until contextualization, HyPE generation, document summaries, and enrichment state are complete for every durable text block:

```bash
READY=0
for _ in $(seq 1 450); do
  docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix \
    python3 /demo-helpers/inspect_namespace.py \
    --db "/data/units/unit-${B_NS}/store.db" \
    > .runs/manual-cortrix/durable-inspection.json
  if python3 - <<'PY'
import json
from pathlib import Path

value = json.loads(Path(".runs/manual-cortrix/durable-inspection.json").read_text())
text_blocks = value["text_blocks"]
assert len(value["documents"]) == 4
assert len(text_blocks) >= 4
assert all(item["contextualized_status"] == 1 for item in text_blocks)
assert value["hype_question_count"] == len(text_blocks) * 3
assert value["document_summary_count"] == 4
assert value["enrich_state_ok_count"] == len(text_blocks)
print({"documents": 4, "text_blocks": len(text_blocks), "hype_questions": value["hype_question_count"], "document_summaries": 4, "pass": True})
PY
  then
    READY=1
    break
  fi
  sleep 2
done
test "$READY" = 1
METRICS_AFTER_READY=0
for _ in $(seq 1 60); do
  if docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix curl -fsS --max-time 10 http://127.0.0.1:9091/metrics > .runs/manual-cortrix/metrics-after-ingest.prom.tmp; then
    METRICS_AFTER_READY=1
    break
  fi
  sleep 2
done
test "$METRICS_AFTER_READY" = 1
mv .runs/manual-cortrix/metrics-after-ingest.prom.tmp .runs/manual-cortrix/metrics-after-ingest.prom
```

Reject the run if contextualization, HyPE, or document-summary failures increased during ingestion:

```bash
python3 - <<'PY'
from pathlib import Path

before = Path(".runs/manual-cortrix/metrics-before-ingest.prom").read_text()
after = Path(".runs/manual-cortrix/metrics-after-ingest.prom").read_text()
keys = {
    "contextualization_failures": 'cortrix_contextual_retrieval_chunks_total{status="failed"}',
    "hype_index_failures": 'cortrix_hype_index_llm_calls_total{status="failed"}',
    "document_summary_failures": 'cortrix_doc_summary_llm_calls_total{status="failed"}',
}

def metric(text, key, required):
    for line in text.splitlines():
        if line.startswith(key + " "):
            return float(line.rsplit(" ", 1)[1])
    if required:
        raise RuntimeError(f"Required metric missing: {key}")
    return 0.0

deltas = {name: metric(after, key, True) - metric(before, key, False) for name, key in keys.items()}
assert all(value == 0 for value in deltas.values()), deltas
print({**deltas, "pass": True})
PY
```

Expected output:

```text
{'contextualization_failures': 0.0, 'hype_index_failures': 0.0, 'document_summary_failures': 0.0, 'pass': True}
```

The reference run completed with:

```text
{'documents': 4, 'text_blocks': 5, 'hype_questions': 15, 'document_summaries': 4, 'pass': True}
```

## 5. Read and submit the query

Read the frozen query and keep it in the shell:

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/order-api-field-migration/fixtures/query.txt").read_text().strip())'
QUERY="$(python3 -c 'from pathlib import Path; print(Path("scenarios/order-api-field-migration/fixtures/query.txt").read_text().strip())')"
export QUERY
```

Build the exact Full Stack request used by the reference run:

```bash
python3 - <<'PY' > .runs/manual-cortrix/query-request.json
import json
import os

print(json.dumps({
    "query": os.environ["QUERY"],
    "top_k": 4,
    "rerank": True,
    "include_sources": True,
    "route": "complex",
    "crag": False,
    "granularity": "chunk",
    "explain": True,
    "search_config": {"enable_vector": True, "enable_bm25": True, "enable_sql": False},
    "rag_fusion": True,
    "rag_fusion_config": {
        "enabled": True,
        "variant_count": 3,
        "timeout_ms": 120000,
        "locale": "en",
        "candidate_multiplier": 5,
        "max_candidates": 20,
        "final_rerank": True,
        "activation_policy": "always"
    },
    "llm_rerank": True,
    "llm_rerank_config": {
        "enabled": True,
        "top_n": 4,
        "timeout_ms": 120000,
        "locale": "en",
        "consensus_runs": 1
    },
    "namespaces": [os.environ["B_NS"]]
}, indent=2))
PY
```

Submit the request twice, serially, to test repeatability:

```bash
for NUMBER in 01 02; do
  curl -fsS --max-time 360 \
    -H 'Accept: application/json' \
    -H 'Content-Type: application/json' \
    --data-binary @.runs/manual-cortrix/query-request.json \
    'http://127.0.0.1:18420/api/v1/query?explain=true' \
    > ".runs/manual-cortrix/query-response-${NUMBER}.json"
done
```

These requests invoke DeepSeek query fusion and listwise reranking. Do not repeat them automatically after a deterministic assertion failure.

## 6. Inspect the ranking

Join the durable child identity to the fixture metadata, then display the three independent ranking responsibilities:

```bash
python3 - <<'PY'
import json
from pathlib import Path

fixture_root = Path("scenarios/order-api-field-migration/fixtures")
manifest = json.loads((fixture_root / "manifest.json").read_text())
durable = json.loads(Path(".runs/manual-cortrix/durable-inspection.json").read_text())
response = json.loads(Path(".runs/manual-cortrix/query-response-01.json").read_text())

document_by_child = {item["child_id"]: item["document_id"] for item in durable["text_blocks"]}
metadata_by_document = {item["document_id"]: item for item in manifest["documents"]}

def project(item, final_rank):
    document_id = document_by_child[item["child_id"]]
    metadata = metadata_by_document[document_id]
    return {
        "document_id": document_id,
        "version": metadata["version"],
        "lifecycle_status": metadata["status"],
        "final_response_rank": final_rank,
        "bge_rerank_score": item["rerank_score"],
    }

projected = [project(item, rank) for rank, item in enumerate(response["results"], start=1)]
bge_leader = max(projected, key=lambda item: item["bge_rerank_score"])
final_top = projected[0]
resolver = next(item for item in projected if item["lifecycle_status"] == "current")
selected_response = response["results"][resolver["final_response_rank"] - 1]
expected_field = manifest["resolver"]["expected_field"]
selected_content_contains_expected_field = isinstance(selected_response.get("content"), str) and expected_field in selected_response["content"]
explain = response["explain"]
required_paths = {"dense", "fts5", "contextualized", "hype_question", "sparse"}
result = {
    "retrieval_paths": explain["rrf_path_counts"],
    "rag_fusion": explain["llm_dependent_features"]["rag_fusion"],
    "listwise_rerank": explain["llm_dependent_features"]["llm_rerank"],
    "bge_leader": bge_leader,
    "final_top_result": final_top,
    "resolver_decision": {
        "selected_document_id": resolver["document_id"],
        "selected_version": resolver["version"],
        "selected_field": expected_field,
        "selected_content_contains_expected_field": selected_content_contains_expected_field,
        "action": "preserved_final_top1" if resolver == final_top else "changed_final_top1",
    },
}
assert explain["granularity"] == "chunk"
assert required_paths.issubset(result["retrieval_paths"])
assert all(result["retrieval_paths"][path] > 0 for path in required_paths)
assert result["rag_fusion"]["active"] and not result["rag_fusion"]["degraded"]
assert result["listwise_rerank"]["active"] and not result["listwise_rerank"]["degraded"]
assert result["listwise_rerank"]["model"] == "deepseek-v4-flash"
assert bge_leader["document_id"] == "order-api-guide-v1.0"
assert final_top["document_id"] == "order-api-release-v2.0"
assert {"order-api-guide-v1.0", "order-api-release-v2.0"}.issubset({item["document_id"] for item in projected})
assert result["resolver_decision"]["selected_field"] == "buyer_account_id"
assert result["resolver_decision"]["selected_content_contains_expected_field"]
print(json.dumps(result, indent=2))
PY
```

The reference run showed the complete projected JSON below. A new run must match the document identities, lifecycle states, path participation, non-degraded feature state, model identity, field decision, and assertions. Latencies and generated query variants are observations and may differ.

```json
{
  "retrieval_paths": {
    "contextualized": 4,
    "dense": 4,
    "fts5": 4,
    "hype_question": 4,
    "sparse": 4
  },
  "rag_fusion": {
    "active": true,
    "degraded": false,
    "feature_id": "F36",
    "llm_latency_ms": 1569,
    "reason": "active",
    "variant_count": 4,
    "variants_used": [
      "Create order now rejects a payload with account_id as an unknown field. Which request field should replace it?",
      "What field should be used instead of account_id when creating an order, since it is now rejected as unknown?",
      "What are the valid request fields for the create order endpoint?",
      "If account_id is not a valid field for creating an order, what is the correct field to include in the request?"
    ]
  },
  "listwise_rerank": {
    "active": true,
    "degraded": false,
    "feature_id": "F36-LR",
    "llm_calls": 1,
    "llm_latency_ms": 3040,
    "model": "deepseek-v4-flash",
    "order_changed": true,
    "reason": "active",
    "top_n_effective": 4,
    "votes_ok": 1
  },
  "bge_leader": {
    "document_id": "order-api-guide-v1.0",
    "version": "v1.0",
    "lifecycle_status": "superseded",
    "final_response_rank": 2,
    "bge_rerank_score": 0.9467289447784424
  },
  "final_top_result": {
    "document_id": "order-api-release-v2.0",
    "version": "v2.0",
    "lifecycle_status": "current",
    "final_response_rank": 1,
    "bge_rerank_score": 0.6197220683097839
  },
  "resolver_decision": {
    "selected_document_id": "order-api-release-v2.0",
    "selected_version": "v2.0",
    "selected_field": "buyer_account_id",
    "selected_content_contains_expected_field": true,
    "action": "preserved_final_top1"
  }
}
```

## 7. Verify the expected result

Confirm that the two serial responses preserve final order and BGE scores:

```bash
python3 - <<'PY'
import json
from pathlib import Path

first = json.loads(Path(".runs/manual-cortrix/query-response-01.json").read_text())
second = json.loads(Path(".runs/manual-cortrix/query-response-02.json").read_text())
first_ids = [item["child_id"] for item in first["results"]]
second_ids = [item["child_id"] for item in second["results"]]
first_scores = [item["rerank_score"] for item in first["results"]]
second_scores = [item["rerank_score"] for item in second["results"]]
result = {
    "result_order_identical": first_ids == second_ids,
    "rerank_scores_identical": first_scores == second_scores,
}
assert all(result.values())
print(result)
PY
```

Expected output:

```text
{'result_order_identical': True, 'rerank_scores_identical': True}
```

The key result is deliberately layered:

```text
BGE cross-encoder leader: order-api-guide-v1.0 / account_id / superseded
Cortrix final top result: order-api-release-v2.0 / buyer_account_id / current
Application lifecycle resolver: preserved the current final top result
```

## 8. Clean up

Remove only this manual namespace, stop the dedicated services, and delete the runtime file that contained the injected secret:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix \
  python3 /demo-helpers/cleanup_namespaces.py "$B_NS"
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml down --remove-orphans
python3 -c 'from pathlib import Path; Path(".runtime/config/cortrix.yaml").unlink(missing_ok=True)'
unset CORTRIX_LLM_API_KEY DEEPSEEK_API_KEY CORTRIX_LLM_ENABLED CORTRIX_LLM_PROVIDER CORTRIX_LLM_MODEL CORTRIX_LLM_BASE_URL
```

Confirm that the three loopback ports are released:

```bash
for PORT in 18420 19091 15432; do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN | grep -q LISTEN; then
    echo "port ${PORT} is still in use"
    false
  else
    echo "port ${PORT} released"
  fi
done
```

## 9. Understand what happened

```text
four frozen documents
  -> Cortrix Full Stack ingestion
  -> LLM enrichment, contextualization, HyPE questions, document summaries
shared query text
  -> dense + FTS5/BM25 + contextualized + HyPE + sparse recall
  -> RRF fusion
  -> BGE cross-encoder scores
  -> DeepSeek listwise final order
  -> application lifecycle validation
  -> current v2 release bulletin and buyer_account_id
```

The verbose commands, metrics, intermediate JSON, and layer projections are educational diagnostics for this Demo. A production application would normally automate ingestion, telemetry, policy validation, and cleanup, and would expose only the business result and required operational telemetry.

## 10. Keep the claim boundary

This manual run demonstrates the accepted Full Stack contract on one synthetic version-conflict corpus. It does not prove universal retrieval superiority, lower latency, lower cost, or a general database comparison. Internal ingestion and listwise calls do not expose complete token usage, so the run cannot support a public total-cost claim.
