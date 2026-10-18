# Harness adapter

This adapter implements the `pg` and `b` Harness paths defined by `live_three_path/v1`. It pins [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) at commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca` and verifies the checkout commit, clean state, and required built modules before execution.

The checkout path is supplied at runtime through `DEMO_HARNESS_ROOT`; a path or directory name never establishes version identity. The adapter uses the public `cortrix_live_demo_*` receipt schemas and stable adapter version `cortrix_live_demo_harness_v1`.

Harness receives an ephemeral Bearer credential and calls the loopback operator surface. It never reads `DEEPSEEK_API_KEY`. Provider requests remain subject to the controller's explicit external-call authorization, request limits, durable reservation, and budget checks. There is no model fallback and no automatic retry after an uncertain outcome.

Offline transport and contract tests live in `tests/`. The native keyless integration checks require an explicit `DEMO_HARNESS_ROOT` that points to the pinned checkout.
