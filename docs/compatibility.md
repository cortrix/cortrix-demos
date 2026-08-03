# Compatibility

The first scenario separates release identity from source identity:

- Cortrix release: `v1.0.0-rc.1`
- release commit: `e159974f936bd987d5718195d54cd70ff3acc2e5`
- validated source revision: `32b82f6f8f1d7a41349f408969ff03b7997b6c15`

The source revision descends from the release commit and includes the public changes used by the accepted source package. A run must record both identities. It must not describe the source revision as the tag commit.

The Full Stack profile requires PostgreSQL 16, pgvector, BGE-M3, BGE reranker v2 M3, and an external `deepseek-v4-flash` endpoint. Other versions and providers are not accepted by this scenario unless a new compatibility review updates the contract.
