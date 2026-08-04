# Runner

The shared runner owns scenario discovery, technology-profile and adapter validation, public-safety checks, source and runtime preflight, candidate-run state, resolver validation, cleanup, and evidence assembly.

It does not decide that a run is accepted. Independent Clean Run review owns that state transition.

Agent-facing discovery is available through `democtl list --json` and `democtl describe --scenario <id> --json`. Failures use stable JSON error fields rather than requiring an Agent to parse prose.

Use the source checkout and runtime paths through CLI options or ignored runtime state. Do not commit local absolute paths.
