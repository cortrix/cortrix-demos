# Run B: Cortrix Read-Only Plugin

## 1. Question and responsibility boundary

Run B answers the same frozen question with the read-only Cortrix bundle enabled. It may search and read evidence, explain conflicts, and propose read-only checks, but it must not execute DDL, DML, rollback, configuration changes, or traffic changes.

## 2. Controlled environment

The Harness commit, provider, model, answer prompt template, corpus, top k, output contract, timeout, and application resolver are the same as Run A. Run B records `cortrix_bundle_loaded`; this is the only independent variable.

## 3. Evidence acquisition

The runner executes `cortrix_search_evidence` through the real Harness tool pipeline against one operator-fixed Cortrix namespace. It then resolves returned `evidence_ref` values through `cortrix_get_source` in the same durable session and binds each source hash to the frozen fixture manifest.

## 4. Harness answer stage

The canonical Cortrix evidence is passed to the same DeepSeek Harness answer prompt used by Run A. The answer must cite only supplied evidence references and express the current field, rollback decision, and action mode in the frozen structured contract.

## 5. Application resolver

The resolver requires the current migration source, `buyer_account_id`, a closed rollback window, and `read_only_diagnosis`. Cortrix supplies retrieval evidence; the resolver independently owns source authority and allowed actions.

## 6. Expected result

Run B should select `orders-schema-migration-v4.0-current`, identify `buyer_account_id`, state that rollback is no longer permitted, and limit the plan to catalog inspection, deployed statement inspection, and optional `EXPLAIN` without `ANALYZE` in a read-only transaction.

## 7. Evidence and limits

The accepted viewer must keep plugin retrieval and application authority visually separate. One accepted trace demonstrates the integration mechanism and does not establish general retrieval superiority, production safety, or benchmark quality.
