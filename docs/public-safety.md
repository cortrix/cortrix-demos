# Public-Safety Contract

The repository was staged privately during bootstrap. Every tracked file and GitHub interaction must now remain safe for a public repository and its history.

The validator rejects:

- CJK characters in the canonical `main` tree
- private workspace names and local absolute paths
- internal review or control-plane references
- secret-like assignments and common private-key markers
- private IPv4 literals; loopback addresses remain allowed
- tracked runtime caches, logs, environment files, or candidate runs
- a missing or non-Apache-2.0 root `LICENSE`, or a missing `NOTICE`
- GitHub Actions workflow YAML in the initial bootstrap

The presence of an environment-variable name in documentation is allowed. A value, assignment, or captured environment dump is not.

The public repository already contains a frozen set of historical acceptance and campaign identifiers in previously published evidence and its compatibility code. The scanner records the exact file and occurrence count for those legacy values. A missing or additional occurrence fails validation. New code, documentation, and evidence must use `independent_clean_room`, `foundation`, or another public-neutral identity.

`public-safety` reports `pass_with_frozen_legacy_exceptions` while those exact archives remain in the current tree. A future clean accepted run may remove the compatibility exceptions; the project does not rewrite historical observations to make the count disappear.

Before a public pull request, run `make public-history-safety BASE_REF=origin/main`. It scans the commit metadata and every text file in every commit after the public base. A clean final tree cannot hide an unsafe intermediate commit.
