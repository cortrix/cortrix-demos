# Orders SDK 2.x retry contract tests

Status: current verification reference.

The maintained contract suite asserts that `max_attempts=3` produces three total calls, not one initial call plus three retries. It also asserts retry for 429 and 503, no retry for an unlisted 500 response, and separate handling for transport errors.
