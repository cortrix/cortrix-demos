# Public-Safety Contract

The repository is private during bootstrap, but every tracked file must already be safe for a future public history.

The validator rejects:

- CJK characters in the canonical `main` tree
- private workspace names and local absolute paths
- internal review or control-plane references
- secret-like assignments and common private-key markers
- private IPv4 literals outside the single governed local viewer default in `Makefile`; loopback addresses remain allowed
- tracked runtime caches, logs, environment files, or candidate runs
- a missing or non-Apache-2.0 root `LICENSE`, or a missing `NOTICE`
- GitHub Actions workflow YAML in the initial bootstrap

The presence of an environment-variable name in documentation is allowed. A value, assignment, or captured environment dump is not.
