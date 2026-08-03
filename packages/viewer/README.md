# Evidence viewer

The viewer is a static, read-only surface for an accepted run. It refuses to present a result unless the scenario pointer names an accepted manifest and the manifest itself reports `accepted`.

Serve the repository root with `make viewer`, then open the scenario page through the address printed by the server. The viewer uses DOM text nodes for all evidence-derived values and does not evaluate evidence content.
