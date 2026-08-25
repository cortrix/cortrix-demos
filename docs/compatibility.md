# Compatibility

The first scenario separates release identity from source identity:

- Cortrix release: `v1.0.0-rc.1`
- release commit: `e159974f936bd987d5718195d54cd70ff3acc2e5`
- validated source revision: `32b82f6f8f1d7a41349f408969ff03b7997b6c15`

The source revision descends from the release commit and includes the public changes used by the accepted source package. A run must record both identities. It must not describe the source revision as the tag commit.

The Full Stack profile requires PostgreSQL 16, pgvector, BGE-M3, BGE reranker v2 M3, and an external `deepseek-v4-flash` endpoint. Other versions and providers are not accepted by this scenario unless a new compatibility review updates the contract.

## DeepSeek Harness integration

The four Harness scenarios require:

- DeepSeek Harness commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca` and package family `0.1.0-rc.7`;
- `@cortrix/dsh-cortrix` `0.1.0` at Preview maturity;
- Cordis `4.0.1` and Schemastery `3.18.1`;
- Cortrix query API commit `4c0f0f96b652d5662a66d047771826a4d2933739`;
- top-level Native tool calls and the exact two-tool read-only surface;
- the model assets and checksums in [Model asset preparation](model-assets.md).

A different integration source commit, Harness commit, package family, durable metadata contract, tool schema, Cortrix query contract, model, or application resolver requires a new compatibility review and accepted run.
