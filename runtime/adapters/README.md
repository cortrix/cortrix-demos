# Runtime adapters

Runtime adapters are reusable implementations selected by a scenario technology profile. A baseline adapter owns Run A integration. An LLM provider adapter owns provider identity, secret discovery, supported models, protocol, and fail-closed capability checks.

Only adapters with `support_status: implemented` may run. `contract_only` entries document a future extension point and must fail before provisioning or external work.

An adapter must not contain business fixtures, expected answers, or scenario assertions. Those belong under `scenarios/<scenario-id>/`.
