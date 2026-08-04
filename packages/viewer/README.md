# Evidence viewer

The viewer is a static, read-only human projection of an accepted Agent-first evidence contract. It refuses to present a result unless the scenario pointer names an accepted manifest, the manifest reports `accepted`, the technology profile matches the scenario, and the layered resolver passes.

Serve the repository root with `make viewer`, then open the scenario page through the address printed by the server. The viewer uses the Cortrix Magma Orange visual identity, official Cortrix logo assets, responsive light/dark themes, a scenario-level Technology Profile, and an Agent Execution Path. Evidence-derived values use DOM text nodes and are never evaluated as code or unsanitized HTML.
