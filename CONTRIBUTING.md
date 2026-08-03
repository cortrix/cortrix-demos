# Contributing

Contributions are welcome after the repository's license and public governance are finalized. Until then, this private candidate is not open for redistribution.

## Development rules

1. Keep shared execution logic under `packages/` and business-specific material under `scenarios/`.
2. Use American English for every tracked surface.
3. Record provenance for every imported or adapted file.
4. Never add secrets, local paths, private review links, raw private logs, or generated runtime caches.
5. Do not make a candidate run accepted in code. Acceptance is a human decision.
6. Run `make validate` before creating a local commit.

The `main` branch is the canonical English surface. Localization branches must not change canonical execution evidence.
