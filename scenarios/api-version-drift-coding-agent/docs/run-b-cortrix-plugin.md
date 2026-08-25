# Run B: Cortrix Read-Only Plugin

## 1. Question and responsibility boundary

Run B answers the same frozen question with the read-only Cortrix bundle enabled. It may search and read evidence, explain version drift, and propose isolated tests, but it must not edit code, call a live API, or recommend the deprecated option as current.

## 2. Controlled environment

The Harness commit, provider, model, answer prompt template, corpus, top k, output contract, timeout, and application resolver are the same as Run A. Run B records `cortrix_bundle_loaded`; this is the only independent variable.

## 3. Evidence acquisition

The runner executes `cortrix_search_evidence` through the real Harness tool pipeline against one operator-fixed Cortrix namespace. It then resolves returned `evidence_ref` values through `cortrix_get_source` in the same durable session and binds each source hash to the frozen fixture manifest.

## 4. Harness answer stage

The canonical Cortrix evidence is passed to the same DeepSeek Harness answer prompt used by Run A. The answer must cite only supplied evidence references and express the current API, attempt semantics, retryable status set, and action mode in the frozen structured contract.

## 5. Application resolver

The resolver requires the current Orders SDK 2.x API, the deprecation notice, `RetryPolicy`, three total attempts for `max_attempts=3`, 429 and 503, and `explanation_and_tests_only`. The current deprecation notice is the preregistered retrieval top result because it directly resolves the version conflict; the application resolver must independently select the official v2 API as the API authority. Cortrix supplies retrieval evidence; the resolver independently owns package scope and action policy.

## 6. Expected result

Run B should explain that `retries` was removed, `max_attempts` includes the initial request, the frozen example permits three total attempts, and only 429 and 503 are listed. The smallest test plan checks 503 then success, an unlisted 500, and a transport error without editing production code.

## 7. Evidence and limits

The accepted viewer must keep plugin retrieval and application authority visually separate. One accepted trace demonstrates the integration mechanism and does not establish general retrieval superiority, production safety, or benchmark quality.
