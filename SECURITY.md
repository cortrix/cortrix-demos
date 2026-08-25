# Security Policy

This public repository must enable GitHub private vulnerability reporting before the Harness integration release is merged. After it is enabled, use the repository's Security tab to report a vulnerability privately. Do not disclose credentials, private data, or an unpatched vulnerability in a public issue.

## Sensitive information

Do not open an issue or commit a file that contains API keys, credentials, private workspace paths, customer data, environment dumps, or raw request headers.

The current technology profile declares `DEEPSEEK_API_KEY`. The runner first checks that environment variable, then an absolute local profile selected by `CORTRIX_LLM_SECRET_FILE`, and finally the user-level default profile at `${XDG_CONFIG_HOME:-$HOME/.config}/cortrix/secrets/llm/current.yaml`. It resolves a profile only after an authorized Full Stack command reaches preflight; discovery, validation, accepted replay, and the viewer never read it.

On POSIX systems, a resolved profile must be owned by the current user and inaccessible to group and other users. Its model and endpoint must match the scenario contract. Output records only the source class, never the local path or key. A future provider profile must still declare its own secret environment name. The runner may create a mode-`0600` ignored runtime configuration when required by the pinned Cortrix revision. Cleanup must remove that file and record only whether removal succeeded. A key value must never enter evidence, logs, screenshots, or Git history.

## Untrusted model output

LLM output is data, not code. The runner validates structured output before use. The viewer renders content with text-only DOM APIs and does not use dynamic code evaluation or unsanitized HTML insertion.

## Reporting

If private vulnerability reporting is unavailable, the release is blocked until the maintainers provide a public, verified security contact.
