# Public-Safety Contract

The repository is private during bootstrap, but every tracked file must already be safe for a future public history.

The validator rejects:

- CJK characters in the canonical `main` tree
- private workspace names and local absolute paths
- internal review or control-plane references
- secret-like assignments and common private-key markers
- tracked runtime caches, logs, environment files, or candidate runs
- a root `LICENSE` before the license gate is accepted
- GitHub Actions workflow YAML in the initial bootstrap

The presence of an environment-variable name in documentation is allowed. A value, assignment, or captured environment dump is not.
