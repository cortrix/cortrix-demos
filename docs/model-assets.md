# Model Asset Preparation

Live execution requires four local model assets in the Cortrix data volume. Accepted replay does not require them.

| Component | Pinned conversion source | Source path | Size | Required SHA-256 | Attributed upstream |
| --- | --- | --- | ---: | --- | --- |
| Embedding model | `onnx-community/bge-m3-ONNX@25b9af8e87a38eb120cfe87125383677b9cd309e` | `onnx/model_quantized.onnx` | 568,479,395 | `2237f770aad5c71bbc1fc2d361a57f9a37400574cc9eff32626f0cdb49234730` | `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`, MIT |
| Embedding tokenizer | `onnx-community/bge-m3-ONNX@25b9af8e87a38eb120cfe87125383677b9cd309e` | `tokenizer.json` | 17,082,799 | `249df0778f236f6ece390de0de746838ef25b9d6954b68c2ee71249e0a9d8fd4` | `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`, MIT |
| Reranker model | `onnx-community/bge-reranker-v2-m3-ONNX@6f5ff65298512715a1e669753bc754d2bc8f367b` | `onnx/model_quantized.onnx` | 570,727,094 | `912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d` | `BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, Apache-2.0 |
| Reranker tokenizer | `onnx-community/bge-reranker-v2-m3-ONNX@6f5ff65298512715a1e669753bc754d2bc8f367b` | `tokenizer.json` | 17,082,900 | `8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3` | `BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, Apache-2.0 |

The identity above comes from the public Cortrix source at commit `4c0f0f96b652d5662a66d047771826a4d2933739`: [`deploy/model-manifest.tsv`](https://github.com/cortrix/cortrix/blob/4c0f0f96b652d5662a66d047771826a4d2933739/deploy/model-manifest.tsv) and its fail-closed [`deploy/download-models.sh`](https://github.com/cortrix/cortrix/blob/4c0f0f96b652d5662a66d047771826a4d2933739/deploy/download-models.sh). On 2026-08-25, the public GitHub API resolved that exact Cortrix commit, and the public Hugging Face APIs reported both conversion repositories as ungated and returned the same four byte counts and LFS SHA-256 values. This closes the earlier source-provenance gap without re-exporting or redistributing model weights.

## Prepare the exact model cache

Run these commands from the Demos repository root. They build the pinned Cortrix image from public source, use the downloader and manifest embedded in that image, and populate the campaign's external Docker volume. The download is approximately 1.2 GB and makes no external language model call.

```bash
CORTRIX_REV=4c0f0f96b652d5662a66d047771826a4d2933739
CORTRIX_SOURCE=.runtime/cortrix-harness-src
CORTRIX_HARNESS_VOLUME=cortrix_demos_harness_foundation_data

git clone https://github.com/cortrix/cortrix.git "$CORTRIX_SOURCE"
git -C "$CORTRIX_SOURCE" checkout "$CORTRIX_REV"
test "$(git -C "$CORTRIX_SOURCE" rev-parse HEAD)" = "$CORTRIX_REV"

docker build \
  --build-arg "CORTRIX_SOURCE_REVISION=$CORTRIX_REV" \
  --file "$CORTRIX_SOURCE/deploy/Dockerfile" \
  --tag cortrix:quickstart \
  "$CORTRIX_SOURCE"

test "$(docker image inspect cortrix:quickstart --format '{{index .Config.Labels \"org.opencontainers.image.revision\"}}')" = "$CORTRIX_REV"
docker volume create "$CORTRIX_HARNESS_VOLUME"
docker run --rm \
  --volume "$CORTRIX_HARNESS_VOLUME:/data" \
  --entrypoint /app/scripts/download-models.sh \
  cortrix:quickstart \
  /data/models
```

Verify the installed bytes without network access:

```bash
docker run --rm --network none \
  --volume "$CORTRIX_HARNESS_VOLUME:/data:ro" \
  --entrypoint sha256sum \
  cortrix:quickstart \
  /data/models/bge-m3/model.onnx \
  /data/models/bge-m3/tokenizer.json \
  /data/models/bge-reranker-v2-m3/model.onnx \
  /data/models/bge-reranker-v2-m3/tokenizer.json
```

The output must match the four SHA-256 values in the table, in the same order. Any revision, size, checksum, license, or image-label mismatch stops the live campaign. This repository does not redistribute model weights.
