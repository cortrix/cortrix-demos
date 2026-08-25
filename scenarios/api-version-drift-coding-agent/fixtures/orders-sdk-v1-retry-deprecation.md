# Orders SDK retry option deprecation notice

Status: current deprecation notice.

The `retries` constructor option and its retry-count semantics were removed in Orders SDK 2.0. Applications must provide a `RetryPolicy`. Copying a 1.x `retries=3` example into a 2.x client is obsolete and can either fail validation or create an incorrect expectation about total attempts.
