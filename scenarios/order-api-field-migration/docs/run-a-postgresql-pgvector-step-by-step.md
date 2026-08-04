# Run A Manual Runbook: PostgreSQL and pgvector

This Runbook reproduces Run A with direct Docker, HTTP, Python, and SQL commands. It does not use `democtl` to execute the path.

PostgreSQL and pgvector own storage and ranking. The embedding-only Cortrix runtime is used only to generate the same pinned BGE-M3 vectors used by Run B. It makes zero DeepSeek calls and does not use Cortrix retrieval, RRF, reranking, listwise ordering, or lifecycle resolution. Replacing that embedding step with another model would no longer reproduce the accepted comparison.

The output excerpts come from accepted run `order-api-field-migration-20260804T085505Z`. Opaque block IDs and a later run timestamp may differ, but the document order and assertions must match.

## 1. Confirm the shared contract

Run all commands from the repository root. Confirm the frozen question:

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/order-api-field-migration/fixtures/query.txt").read_text().strip())'
```

Expected output:

```text
Create order now rejects a payload with account_id as an unknown field. Which request field should replace it?
```

Confirm that the fixture manifest contains four documents and that all declared checksums match:

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

Expected output:

```text
{'documents': 4, 'checksums': 'pass'}
```

## 2. Prepare the pinned runtime

The Cortrix image must come from source revision `32b82f6f8f1d7a41349f408969ff03b7997b6c15`. If the image is not already present, prepare it from a local source checkout:

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

Materialize the tracked embedding-only configuration. It contains no API key:

```bash
mkdir -p .runtime/config .runs/manual-postgresql
cp runtime/config/cortrix.embedding-only.yaml .runtime/config/cortrix.yaml
chmod 600 .runtime/config/cortrix.yaml
export CORTRIX_LLM_ENABLED=false
```

Create unique namespace names for this manual session:

```bash
MANUAL_SUFFIX="manual-$(date -u +%Y%m%dT%H%M%SZ | tr '[:upper:]' '[:lower:]')"
DOC_NS="order-a-docs-${MANUAL_SUFFIX}"
QUERY_NS="order-a-query-${MANUAL_SUFFIX}"
export DOC_NS QUERY_NS
printf 'DOC_NS=%s\nQUERY_NS=%s\n' "$DOC_NS" "$QUERY_NS"
```

## 3. Start the services

Start PostgreSQL first, then the embedding-only Cortrix service:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml up -d postgres
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml up -d --force-recreate cortrix
```

Wait for both health checks:

```bash
until docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T postgres pg_isready -U cortrix_demo -d cortrix_demo >/dev/null; do sleep 2; done
until curl -fsS http://127.0.0.1:18420/api/v1/system/health/ready >/dev/null; do sleep 2; done
```

Inspect the actual database versions:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T postgres \
  psql -X -U cortrix_demo -d cortrix_demo -At -F ',' \
  -c "SELECT current_setting('server_version'), extversion FROM pg_extension WHERE extname = 'vector';"
```

The reference run returned:

```text
16.14 (Debian 16.14-1.pgdg12+1),0.8.6
```

Verify the exact BGE-M3 files used to create both document and query vectors:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix sh -c '
printf "%s  %s\n" \
  2237f770aad5c71bbc1fc2d361a57f9a37400574cc9eff32626f0cdb49234730 /data/models/bge-m3/model.onnx \
  249df0778f236f6ece390de0de746838ef25b9d6954b68c2ee71249e0a9d8fd4 /data/models/bge-m3/tokenizer.json \
  | sha256sum -c -
'
```

Expected output:

```text
/data/models/bge-m3/model.onnx: OK
/data/models/bge-m3/tokenizer.json: OK
```

## 4. Load the comparison data

Create a Cortrix namespace, upload the four fixtures, and wait for the embedding-only document tasks. This is a direct call to the Cortrix HTTP API, not a Demo runner command:

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
namespace = os.environ["DOC_NS"]
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

Expected document-level result:

```text
{'document': 'order-api-guide-v1.0', 'status': 'completed'}
{'document': 'order-api-release-v2.0', 'status': 'completed'}
{'document': 'order-api-list-pagination-v2.0', 'status': 'completed'}
{'document': 'order-api-cancellation-v2.0', 'status': 'completed'}
```

The exact successful terminal word may be `ready`, `completed`, `success`, or `succeeded` on a compatible runtime.

## 5. Read and submit the query

Read the same query again and keep it in the shell:

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/order-api-field-migration/fixtures/query.txt").read_text().strip())'
QUERY="$(python3 -c 'from pathlib import Path; print(Path("scenarios/order-api-field-migration/fixtures/query.txt").read_text().strip())')"
export QUERY
```

Create a separate query namespace and upload the query text as one embedding anchor:

```bash
python3 - <<'PY'
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

base = "http://127.0.0.1:18420/api/v1"
namespace = os.environ["QUERY_NS"]

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
_, accepted = call(
    "POST",
    "/documents",
    {
        "namespace": namespace,
        "filename": "query-anchor.txt",
        "content": os.environ["QUERY"],
        "metadata": {"document_id": "query-anchor", "role": "query_embedding_anchor", "manual_run": True},
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
        print({"query_anchor": state})
        break
    if state in {"failed", "cancelled", "canceled", "error"}:
        raise RuntimeError(progress)
    time.sleep(1)
else:
    raise TimeoutError(task_id)
PY
```

Export the document and query vectors from the two durable namespaces:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix \
  python3 /demo-helpers/extract_vectors.py \
  --db "/data/units/unit-${DOC_NS}/store.db" \
  --wal "/data/units/unit-${DOC_NS}/hnsw.wal" \
  --dimension 1024 \
  --output /data/manual-document-vectors.json
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml cp \
  cortrix:/data/manual-document-vectors.json .runs/manual-postgresql/document-vectors.json

docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix \
  python3 /demo-helpers/extract_vectors.py \
  --db "/data/units/unit-${QUERY_NS}/store.db" \
  --wal "/data/units/unit-${QUERY_NS}/hnsw.wal" \
  --dimension 1024 \
  --output /data/manual-query-vectors.json
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml cp \
  cortrix:/data/manual-query-vectors.json .runs/manual-postgresql/query-vectors.json
```

Build the SQL from the exported vectors. This step stores version and lifecycle metadata for observation, but neither field participates in ranking:

```bash
python3 - <<'PY' > .runs/manual-postgresql/load-and-query.sql
import json
from pathlib import Path

fixture_root = Path("scenarios/order-api-field-migration/fixtures")
manifest = json.loads((fixture_root / "manifest.json").read_text())
document_records = json.loads(Path(".runs/manual-postgresql/document-vectors.json").read_text())["records"]
query_records = json.loads(Path(".runs/manual-postgresql/query-vectors.json").read_text())["records"]

def quote(value):
    return "'" + str(value).replace("'", "''") + "'"

def vector(values):
    return "[" + ",".join(format(float(value), ".9g") for value in values) + "]"

query_matches = [item for item in query_records if item.get("document_id") == "query-anchor" and item.get("block_type") == 1]
assert len(query_matches) == 1
query_vector = quote(vector(query_matches[0]["embedding"])) + "::vector"
rows = []
for fixture in manifest["documents"]:
    matches = [item for item in document_records if item.get("document_id") == fixture["document_id"] and item.get("block_type") == 1]
    assert matches, fixture["document_id"]
    for item in sorted(matches, key=lambda value: (value["chunk_index"], value["block_id"])):
        assert len(item["embedding"]) == 1024
        rows.append(
            "(" + ",".join(
                [
                    quote(item["block_id"]),
                    quote(fixture["document_id"]),
                    str(int(item["chunk_index"])),
                    quote(fixture["document_id"]),
                    quote(fixture["version"]),
                    quote(fixture["status"]),
                    quote(fixture["effective_at"]),
                    quote(fixture["path"]),
                    quote(item.get("content", "")),
                    quote(vector(item["embedding"])) + "::vector",
                ]
            ) + ")"
        )

print("TRUNCATE TABLE semantic_blocks;")
print("INSERT INTO semantic_blocks (block_id, doc_id, chunk_index, title, version, lifecycle_status, effective_at, source_uri, content, embedding) VALUES " + ",".join(rows) + ";")
print(
    "SELECT row_number() OVER (ORDER BY embedding <=> {query}, doc_id, chunk_index) AS rank, "
    "doc_id, chunk_index, version, lifecycle_status, 1 - (embedding <=> {query}) AS cosine_similarity "
    "FROM semantic_blocks ORDER BY embedding <=> {query}, doc_id, chunk_index;".format(query=query_vector)
)
PY
```

Execute the SQL directly in PostgreSQL:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T postgres \
  psql -X -v ON_ERROR_STOP=1 -U cortrix_demo -d cortrix_demo \
  < .runs/manual-postgresql/load-and-query.sql
```

## 6. Inspect the ranking

The reference run returned this order:

| Rank | Document | Version | Lifecycle | Cosine similarity |
| ---: | --- | --- | --- | ---: |
| 1 | `order-api-guide-v1.0` | `v1.0` | `superseded` | `0.7531767425327823` |
| 2 | `order-api-guide-v1.0` | `v1.0` | `superseded` | `0.6072149968938516` |
| 3 | `order-api-release-v2.0` | `v2.0` | `current` | `0.5937288161355068` |
| 4 | `order-api-cancellation-v2.0` | `v2.0` | `current` | `0.5611662007073772` |
| 5 | `order-api-list-pagination-v2.0` | `v2.0` | `current` | `0.49156024800547193` |

Opaque block IDs may differ. The important observation is that the detailed superseded v1 guide is the strict dense top result, while the current v2 release bulletin is present but lower.

## 7. Verify the expected result

The SQL contains only this ranking expression:

```sql
ORDER BY embedding <=> query_vector, doc_id, chunk_index
```

It does not use `version`, `lifecycle_status`, `effective_at`, or `superseded_by`. Therefore the baseline answer follows the rank-1 v1 guide and points to the retired `account_id` field.

This is the intended Run A result:

```text
Selected document: order-api-guide-v1.0
Selected field: account_id
Lifecycle: superseded
```

## 8. Clean up

Remove only the two namespaces created by this manual Run A, stop the dedicated services, and delete the materialized runtime config:

```bash
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml exec -T cortrix \
  python3 /demo-helpers/cleanup_namespaces.py "$DOC_NS" "$QUERY_NS"
docker-compose -p cortrix_demos_order_api -f runtime/docker-compose.yml down --remove-orphans
python3 -c 'from pathlib import Path; Path(".runtime/config/cortrix.yaml").unlink(missing_ok=True)'
```

Model caches and Docker volumes remain available for Run B.

## 9. Understand what happened

```text
four frozen documents
  -> embedding-only Cortrix ingestion
  -> pinned BGE-M3 document vectors
shared query text
  -> embedding-only Cortrix query anchor
  -> pinned BGE-M3 query vector
document and query vectors
  -> PostgreSQL semantic_blocks
  -> pgvector exact cosine
  -> superseded v1 guide at rank 1
```

The verbose commands and intermediate files are educational diagnostics for this Demo. A production application would normally automate vector generation, ingestion, observability, and cleanup, and would expose only the business result and required operational telemetry.

## 10. Keep the claim boundary

PostgreSQL and pgvector can filter metadata and support more advanced retrieval designs. This baseline intentionally does not. Run A proves only that this frozen BGE-M3 dense-only exact-cosine profile prefers the more similar outdated guide on this synthetic corpus. It is not a performance benchmark or a statement about PostgreSQL's maximum capability.
