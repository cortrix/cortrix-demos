# Technology profiles

A technology profile records the exact technical choices made for one scenario. It is not a repository-wide default and it is not an automatic benchmark matrix.

## Required identity

```json
{
  "schema_version": 1,
  "id": "example-profile",
  "scenario_id": "example-scenario",
  "baseline": {
    "adapter_id": "elasticsearch",
    "role": "run_a",
    "version": "pin-an-exact-version"
  },
  "cortrix": {
    "role": "run_b",
    "release": "pin-a-release",
    "source_revision": "pin-a-source-revision"
  },
  "llm": {
    "adapter_id": "openai-responses",
    "provider": "openai",
    "model": "pin-an-exact-mini-model",
    "secret_env": "OPENAI_API_KEY",
    "roles": ["query_fusion"],
    "local_fallback_allowed": false
  }
}
```

Elasticsearch, MongoDB, and OpenAI entries in the adapter registry are currently `contract_only`. They show how a future scenario can express those choices; they are not runnable integrations.

## Adding a baseline adapter

The adapter must declare engine identity, exact supported versions, provisioning, query behavior, result schema, cleanup, and whether it makes external calls. It must expose a generic `baseline-result` contract so scenario evidence does not use vendor-specific filenames.

## Adding an LLM provider adapter

The adapter must declare provider, protocol, base endpoint identity, supported models, secret environment name, supported roles, usage extraction, pricing source, retry categories, and local-fallback policy. Provider-specific evidence labels map to generic capabilities such as `llm_ingestion`, `llm_query_fusion`, and `llm_listwise_rerank`.

Never put a key in a profile. Never silently replace a model at runtime. A provider/model change creates a new profile version and candidate run.
