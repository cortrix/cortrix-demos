# Orders SDK 2.x retry migration guide

Replace `retries=n` with an explicit `RetryPolicy`. Translate the desired total request count deliberately because 1.x counted retries after the initial request while 2.x `max_attempts` includes it.

Smallest useful test plan:

1. Stub a 503 response followed by success and assert no more than three total calls for `max_attempts=3`.
2. Stub a non-listed 500 response and assert that the policy does not retry it.
3. Stub a transport error and assert the configured transport-error behavior.
4. Keep the test isolated from real network calls and do not edit production code during diagnosis.
