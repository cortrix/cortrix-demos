# Security Policy

This private bootstrap is not yet a published security-support channel.

## Sensitive information

Do not open an issue or commit a file that contains API keys, credentials, private workspace paths, customer data, environment dumps, or raw request headers.

The runner reads `DEEPSEEK_API_KEY` from the environment and may create a mode-`0600` ignored runtime configuration when required by the pinned Cortrix revision. Cleanup must remove that file and record only whether removal succeeded. The key value must never enter evidence, logs, screenshots, or Git history.

## Untrusted model output

LLM output is data, not code. The runner validates structured output before use. The viewer renders content with text-only DOM APIs and does not use dynamic code evaluation or unsanitized HTML insertion.

## Reporting

For now, report a suspected vulnerability privately to the Cortrix maintainers. A public reporting address and response policy will be added before public visibility is enabled.
