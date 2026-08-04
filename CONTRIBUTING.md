# Contributing

Contributions are welcome under Apache License 2.0. Unless explicitly stated otherwise, an intentionally submitted contribution is licensed under the same terms.

## Development rules

1. Keep business questions, fixtures, assertions, and presentation under `scenarios/<scenario-id>/`.
2. Keep reusable baseline and LLM integrations under `runtime/adapters/` and shared runner code.
3. Register scenarios and adapters in their machine-readable registries.
4. Add symmetric scenario-specific Run A and Run B entry guides plus symmetric pipeline step-by-step Runbooks under `scenarios/<scenario-id>/docs/`, then link all four from the root README.
5. Keep `agent.json`, root `AGENTS.md`, and scenario discovery synchronized so a first-time Agent can start without private knowledge.
6. Mark an adapter `implemented` only after fail-closed code, tests, cleanup, and fresh-clone validation exist.
7. Use American English for every tracked surface on `main`.
8. Record provenance for every imported or adapted file.
9. Never add secrets, local paths, private review links, raw private logs, or runtime caches.
10. Never promote a candidate to accepted evidence without independent Clean Run acceptance.
11. Run `make validate` before creating a local commit.

Read [Agent quick start](docs/agent-quickstart.md), [Repository architecture](docs/architecture.md), [Technology profiles](docs/technology-profiles.md), and [Authoring a demo](docs/authoring-a-demo.md) before implementation.
