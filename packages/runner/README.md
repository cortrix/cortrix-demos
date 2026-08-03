# Runner

The shared runner owns scenario validation, public-safety checks, source and runtime preflight, candidate-run state, resolver validation, cleanup, and evidence assembly.

It does not decide that a run is accepted. Human review owns that state transition.

Use the source checkout and runtime paths through CLI options or ignored runtime state. Do not commit local absolute paths.
