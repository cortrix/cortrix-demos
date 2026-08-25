# Orders SDK 2.x retry API

Status: current official API. Effective: 2026-07-20.

Configure retries with `RetryPolicy(max_attempts=3, retryable_statuses={429, 503}, retry_transport_errors=True)`. `max_attempts` includes the initial request, so this policy permits at most three total attempts.

The SDK does not retry every 5xx response by default. The explicit status set in this example contains only 429 and 503. Transport errors remain separately controlled by `retry_transport_errors`.
