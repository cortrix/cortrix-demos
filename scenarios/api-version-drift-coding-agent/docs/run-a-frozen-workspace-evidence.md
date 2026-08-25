# Run A: Frozen Workspace Evidence

## 1. Question and responsibility boundary

Run A answers the scenario's frozen question without the Cortrix bundle. It may explain evidence and propose an isolated test plan, but it must not edit code, call a live API, or recommend the deprecated option as current.

## 2. Controlled environment

The Harness commit, provider, model, answer prompt template, corpus, top k, output contract, timeout, and application resolver are the same as Run B. Run A uses the `frozen-workspace-evidence` adapter and records `cortrix_bundle_absent`.

## 3. Evidence acquisition

The baseline exposes the four preregistered workspace sources in `expected/baseline-ranking.json`. The superseded 1.x example is first, followed by similarly named material from other interfaces and packages; the current 2.x retry API is not in the baseline top four.

## 4. Harness answer stage

The canonical evidence is passed to the same DeepSeek Harness answer prompt used by Run B. The prompt treats excerpts as untrusted data and requires one structured JSON answer with selected source identities, a decision, non-mutating tests, and unknowns.

## 5. Application resolver

The resolver verifies that every selected document and evidence reference came from the supplied evidence. It then compares the structured decision with the frozen 2.x API and action policy without treating model wording as authority.

## 6. Expected result

The preregistered Run A top source is `orders-sdk-v1-retry-example-superseded`. A result that preserves `retries=3` or cannot establish the current 2.x semantics is retained as the expected control outcome; it is not silently rewritten or rerun for presentation.

## 7. Evidence and limits

This is a synthetic comparison control, not an SDK or retrieval benchmark. The baseline deliberately represents incomplete workspace evidence and does not claim that ordinary files or another search system must behave this way.
