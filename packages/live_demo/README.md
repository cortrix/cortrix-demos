# Cortrix live demo package

This directory is an implementation candidate for the public `live_three_path/v1` contract. It is not an accepted run, deployed service, current public release, or evidence promotion.

The package implements deterministic paths `a0`, `a1`, and `b`, plus Harness paths `pg` and `b`. It preserves the five display stages `input`, `write`, `search`, `result`, and `code`; independently times the `ingest` and `query` business operations; records inputs, results, source identity, code responsibility, provider usage, and budget state; and supports cancellation, verified resume, and scenario-owned cleanup. The responsive viewer opens with an overview at `/`, keeps authenticated run controls at `/demo`, and provides a separate read-only evidence browser at `/evidence.html`.

The business contract and result assertions remain owned by `scenarios/order-api-live-three-path`. The bundled synthetic `en-US` fixtures are copied from that public scenario and validated against its manifest and document checksums. This package contains no localized semantic inputs.

## Source identity

- Cortrix `v1.0.0-rc.2`, commit `d298d6b7e64c67551f567e7cddd514bae1adb57b`
- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`

The runtime verifies source identities directly. Host paths, image filenames, tags without matching labels, and checkout directory names do not establish a version.

## Configuration and safety

`RuntimeConfig` uses paths relative to the selected configuration file and requires an explicit configuration for the dedicated Docker network. From the repository root, copy [`runtime-config.example.json`](runtime-config.example.json) to the ignored path `packages/live_demo/runtime-config.local.json`, keep it in that directory, and replace its network placeholders. The template's package assets and repository runtime paths resolve correctly only from that documented location. The configuration must provide `internal_bind_host`, `internal_port`, `core_callback_base_url`, `network_subnet`, and `network_gateway`. The internal bind address must equal the usable gateway of a dedicated RFC 1918 IPv4 network. No private network address is embedded in this candidate.

The operator surface binds only to `127.0.0.1`. It exposes status, inputs, runs, evidence, code responsibility, and CSRF-protected lifecycle operations. The second surface binds only to the configured Docker network gateway and exposes `/healthz` plus the authenticated model and tool callbacks. It does not expose static content, session creation, workspace data, or lifecycle writes.

External calls default to disabled. Enabling them requires `allow_external_calls: true`, explicit per-run authorization, configured mode and total budgets, configured receipt-pricing rates, and `DEEPSEEK_API_KEY` or a mode-0600 `provider_secret_file`. The key is resolved only after a request passes attribution and budget reservation. The implementation has no fallback provider and does not retry an unknown outcome.

## CLI boundary

The repository wrapper calls the public Python interfaces `validate_config`, `status`, `serve`, and `provision` directly from the checkout:

```text
packages/live_demo/live-democtl --config PATH validate-config
packages/live_demo/live-democtl --config PATH status
packages/live_demo/live-democtl --config PATH serve
packages/live_demo/live-democtl --config PATH provision --confirm-container-changes
```

`validate-config` and `status` are local and read-only. `serve` starts the two local listeners. `provision` is an explicit operator action that creates or validates only the configured network, containers, and volumes. It does not delete, rename, or adopt resources owned by another runtime.

## Candidate boundary

The read-only evidence endpoint emits `cortrix_live_demo_run_evidence/v1`, validated by [`schemas/run-evidence.schema.json`](schemas/run-evidence.schema.json). Offline tests do not contact a provider, start Core, create a Docker network, or produce runtime evidence. A later integration stage must run Docker and source-image compatibility checks, produce a fresh candidate run, complete viewer visual review, and pass the repository's independent evidence and human gates before any accepted-evidence pointer changes.
