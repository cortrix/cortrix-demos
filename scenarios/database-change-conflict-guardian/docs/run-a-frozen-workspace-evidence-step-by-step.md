# Run A Manual Runbook: Frozen Workspace Evidence

Run A is the negative control. A human operator constructs the preregistered frozen workspace evidence, gives it to the pinned DeepSeek Harness answer stage, and then applies the same application resolver used by Run B. Cortrix is not started, the plugin is not loaded, and no retrieval service is queried.

The commands below are designed to be copied from the repository root. Stages 0 through 5 make no external calls. Stage 6 makes exactly one authorized `deepseek/deepseek-v4-flash` call and can resolve the key from the protected default profile; it never prints or stores the secret value.

## Stage 0. Set the run identity and fail closed

```bash
set -euo pipefail
SCENARIO=database-change-conflict-guardian
RUN_ROOT=.runs/manual-harness/$SCENARIO/run-a
HARNESS_ROOT=.runtime/deepseek-harness
mkdir -p "$RUN_ROOT"
test "$(git branch --show-current)" = main
test -z "$(git status --short --untracked-files=all)"
test "$(git -C "$HARNESS_ROOT" rev-parse HEAD)" = 99f6f02fecdb7dff40c3fbc9470f5907c29f74ca
test -z "$(git -C "$HARNESS_ROOT" status --short --untracked-files=all)"
```

Expected result: every `test` exits with status `0` and prints nothing.

## Stage 1. Discover and validate the frozen scenario

```bash
./democtl describe --scenario "$SCENARIO" --json | jq '{id,scenario_version,integration_kind,synthetic_data}'
./democtl validate --scenario "$SCENARIO"
```

Expected key output:

```json
{
  "status": "pass",
  "scenario": "database-change-conflict-guardian",
  "external_calls": 0
}
```

## Stage 2. Read the exact shared question

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/database-change-conflict-guardian/fixtures/query.txt").read_text().strip())'
```

Expected output:

```text
After the order database migration, writes fail because the column name no longer matches. Using only the current approved schema migration, the superseded runbook, the rollback window, and the incident evidence, identify the active field and give a read-only diagnostic plan. Do not execute changes.
```

## Stage 3. Construct the preregistered workspace evidence

```bash
./democtl harness baseline --scenario "$SCENARIO" --output "$RUN_ROOT/evidence.json"
jq '{provider,backend_mode,external_calls,documents:[.evidence[]|{document_id,status,version}]}' "$RUN_ROOT/evidence.json"
```

Expected key output:

```json
{
  "provider": "frozen-workspace-evidence",
  "backend_mode": "cortrix_bundle_absent",
  "external_calls": 0,
  "documents": [
    {"document_id": "orders-schema-runbook-v3.1-superseded", "status": "superseded", "version": "3.1"}
  ]
}
```

The actual array contains four documents. The superseded runbook must remain first, and the current migration is not present in this control evidence.

## Stage 4. Verify every projected source hash

```bash
python3 - "$RUN_ROOT/evidence.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
scenario = Path("scenarios/database-change-conflict-guardian")
evidence = json.loads(Path(sys.argv[1]).read_text())
manifest = json.loads((scenario / "fixtures/manifest.json").read_text())
expected = {item["document_id"]: item["sha256"] for item in manifest["documents"]}
for item in evidence["evidence"]:
    assert item["source_sha256"] == expected[item["document_id"]]
print(json.dumps({"status": "pass", "verified_sources": len(evidence["evidence"]), "external_calls": 0}))
PY
```

Expected output: `{"status": "pass", "verified_sources": 4, "external_calls": 0}`.

## Stage 5. Build and inspect the shared answer contract

```bash
./democtl harness prompt --scenario "$SCENARIO" --evidence "$RUN_ROOT/evidence.json" --output "$RUN_ROOT/answer-prompt.txt"
sed -n '1,4p' "$RUN_ROOT/answer-prompt.txt"
shasum -a 256 "$RUN_ROOT/answer-prompt.txt"
```

The first line must be `Prompt contract: deepseek-harness-cortrix-answer/v2`. The prompt marks evidence as untrusted, forbids tools and mutations, and requires one syntactically valid six-key JSON object with exactly two non-mutating checks.

## Stage 6. Run the pinned Harness answer stage

```bash
python3.14 runtime/harness/run-answer.py \
  --root . \
  --harness-root "$HARNESS_ROOT" \
  --prompt "$RUN_ROOT/answer-prompt.txt" \
  --answer "$RUN_ROOT/answer.json" \
  --usage "$RUN_ROOT/usage.json" \
  --home "$RUN_ROOT/harness-home"
```

Expected key output: `"status": "pass"`, `"provider": "deepseek"`, `"model": "deepseek-v4-flash"`, `"call_count": 1`, and `"secret_value_recorded": false`. If neither explicit environment injection nor the protected default profile is usable, the command stops before an answer is accepted.

## Stage 7. Inspect the structured answer and usage

```bash
jq '{answer,selected_document_ids,evidence_refs,decision,recommended_checks,unknowns}' "$RUN_ROOT/answer.json"
jq '{provider,model,call_count,input_tokens,output_tokens,cache_hit_tokens,secret_source,secret_value_recorded,fallback_used,local_generative_llm}' "$RUN_ROOT/usage.json"
```

Every selected document and evidence reference must come from `evidence.json`. The answer may follow the obsolete `account_id` evidence or declare the current authority unknown; it must not invent a current source or suggest a mutation.

## Stage 8. Apply the application resolver

```bash
./democtl harness resolve \
  --scenario "$SCENARIO" \
  --mode cortrix_bundle_absent \
  --evidence "$RUN_ROOT/evidence.json" \
  --answer "$RUN_ROOT/answer.json" \
  --output "$RUN_ROOT/resolver.json"
jq '{pass,execution_pass,authority_pass,expected_outcome_observed,authority_failures}' "$RUN_ROOT/resolver.json"
```

Expected result: `pass=true`, `execution_pass=true`, `authority_pass=false`, and `expected_outcome_observed=true`. Here `pass` means the negative control behaved as preregistered; it does not mean the stale answer is operationally authoritative.

## Stage 9. Compare the immutable inputs with Run B

```bash
jq -S '{scenario_id,query}' "$RUN_ROOT/evidence.json" | shasum -a 256
grep '^Prompt contract:' "$RUN_ROOT/answer-prompt.txt"
git status --short --untracked-files=all
```

Run B must use the same scenario, question, Harness commit, model, answer contract, corpus, and resolver. Only `cortrix_bundle_loaded` and the evidence it returns may differ. `.runs/` is ignored, so the final Git command must remain empty.

## Stage 10. Preserve the result without promoting it

Keep the ignored run directory for comparison. This manual result is not accepted evidence by itself, cannot be used for an official screenshot, and must never be copied with `harness-home/` into tracked evidence.
