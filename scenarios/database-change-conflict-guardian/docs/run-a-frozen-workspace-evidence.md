# Run A: Frozen Workspace Evidence

## 1. Question and responsibility boundary

Run A answers the scenario's frozen question without the Cortrix bundle. It may explain evidence and propose read-only checks, but it must not execute DDL, DML, rollback, configuration changes, or traffic changes.

## 2. Controlled environment

The Harness commit, provider, model, answer prompt template, corpus, top k, output contract, timeout, and application resolver are the same as Run B. Run A uses the `frozen-workspace-evidence` adapter and records `cortrix_bundle_absent`.

## 3. Evidence acquisition

The baseline exposes the four preregistered workspace sources in `expected/baseline-ranking.json`. The superseded 3.1 runbook is first because it closely mirrors the observed error; the current 4.0 migration is not in the baseline top four.

## 4. Harness answer stage

The canonical evidence is passed to the same DeepSeek Harness answer prompt used by Run B. The prompt treats excerpts as untrusted data and requires one structured JSON answer with selected source identities, a decision, read-only checks, and unknowns.

## 5. Application resolver

The resolver verifies that every selected document and evidence reference came from the supplied evidence. It then compares the structured decision with the frozen current-schema and action policy without treating model wording as authority.

## 6. Expected result

The preregistered Run A top source is `orders-schema-runbook-v3.1-superseded`. A result that does not identify the current 4.0 field is preserved as the expected control outcome; it is not silently rewritten or rerun for presentation.

## 7. Evidence and limits

This is a synthetic comparison control, not a database retrieval benchmark. The baseline deliberately represents incomplete workspace evidence and does not claim that ordinary files, PostgreSQL, or another search system must behave this way.
