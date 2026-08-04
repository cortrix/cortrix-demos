# Contributing

Contributions are welcome under Apache License 2.0. Unless explicitly stated otherwise, an intentionally submitted contribution is licensed under the same terms.

## Development rules

1. Keep business questions, fixtures, assertions, and presentation under `scenarios/<scenario-id>/`.
2. Keep reusable baseline and LLM integrations under `runtime/adapters/` and shared runner code.
3. Register scenarios and adapters in their machine-readable registries.
4. Mark an adapter `implemented` only after fail-closed code, tests, cleanup, and fresh-clone validation exist.
5. Use American English for every tracked surface on `main`.
6. Record provenance for every imported or adapted file.
7. Never add secrets, local paths, private review links, raw private logs, or runtime caches.
8. Never promote a candidate to accepted evidence without independent Clean Run acceptance.
9. Run `make validate` before creating a local commit.

Read [Repository architecture](docs/architecture.md), [Technology profiles](docs/technology-profiles.md), and [Authoring a demo](docs/authoring-a-demo.md) before implementation.
