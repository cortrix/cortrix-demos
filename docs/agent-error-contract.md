# Agent error contract

The `democtl` error envelope lets an Agent decide whether to correct input, wait and retry, or stop without parsing English text.

```json
{
  "error": {
    "code": "CX_DEMO_*",
    "category": "auth|quota|transient|permanent|timeout",
    "retryable": false,
    "message": "Human-readable summary",
    "structured_data": {}
  }
}
```

Retryable errors also include `retry_after_ms`. A safe corrective action appears as `structured_data.next_action`. The absence of `next_action` is intentional for evidence integrity failures, deterministic assertion failures, and invalid internal state.

## Agent decision rules

| Failure class | Contract signal | Agent behavior |
|---|---|---|
| Correctable input or precondition | Distinct code, `retryable: false`, and `structured_data.next_action` | Perform only the stated safe action, then rerun the failed command. |
| Wait and retry | `retryable: true` and `retry_after_ms` | Retry only within the reviewed attempt and cost contract. |
| Terminal integrity or assertion failure | Distinct integrity, assertion, or state code with no `next_action` | Stop and surface the evidence. Do not edit archived evidence, change assertions, or retry automatically. |

`retryable: false` does not always mean that a human can never correct the environment. It means that repeating the same command without a stated corrective action would produce the same result.

## Execution codes

The execution path uses these code families:

| Code or family | Meaning | Recovery rule |
|---|---|---|
| `CX_DEMO_LIVE_INPUT_INVALID` | A live command input is outside the reviewed contract. | Follow `next_action`; a passive retry is not allowed. |
| `CX_DEMO_CHECKOUT_BRANCH_INVALID`, `CX_DEMO_LOCALIZATION_CHECKOUT_INVALID`, `CX_DEMO_WORKING_TREE_DIRTY`, `CX_DEMO_CHECKOUT_COMMIT_INVALID` | The demo checkout does not satisfy a live execution precondition. | Correct only the reported checkout condition. Local filenames are never included in the payload. |
| `CX_DEMO_POSTGRES_SCHEMA_FAILED` | The local PostgreSQL demo volume could not apply the tracked idempotent schema. | Inspect only the local demo volume and tracked schema; do not replace evidence or change scenario inputs. |
| `CX_DEMO_WALKTHROUGH_INPUT_INVALID`, `CX_DEMO_WALKTHROUGH_SESSION_NOT_FOUND`, `CX_DEMO_WALKTHROUGH_PHASE_INVALID` | The walkthrough command, session, or ordering is not ready for the requested step. | Follow the reported safe command or inspect the current walkthrough status. |
| `CX_DEMO_HTTP_RATE_LIMITED`, `CX_DEMO_HTTP_SERVER_ERROR`, `CX_DEMO_OPERATION_TIMEOUT`, `CX_DEMO_INGESTION_TIMEOUT` | A reviewed transient failure occurred. | Use `retry_after_ms` and the existing attempt limit. Do not create extra attempts. |
| `CX_DEMO_FULL_STACK_ATTEMPT_LIMIT_REACHED`, `CX_DEMO_CAMPAIGN_ATTEMPT_CAP_EXCEEDED`, `CX_DEMO_BUDGET_BOUND_EXCEEDED` | An attempt or cost boundary has been reached. | Stop. The error does not grant permission to expand a limit or budget. |
| `CX_DEMO_EXECUTION_ASSERTION_FAILED` | Deterministic runtime output does not satisfy the scenario contract. | Stop and preserve the rejected run. Do not change fixtures or assertions to force acceptance. |
| `CX_DEMO_LIVE_STATE_INVALID`, `CX_DEMO_WALKTHROUGH_STATE_INVALID` | Local execution state is malformed or inconsistent. | Stop and surface the error. Do not repair run history in place. |
| `CX_DEMO_ACCEPTANCE_INTEGRITY_VIOLATION` | Candidate or accepted evidence fails an integrity or identity check. | Stop. Never rewrite evidence to make the check pass. |
| `CX_DEMO_ACCEPTANCE_INPUT_INVALID`, `CX_DEMO_SCREENSHOT_INPUT_INVALID` | A review or screenshot command has a safely correctable input. | Follow `next_action`; do not alter accepted evidence content. |

## Data minimization

Structured data contains only values needed for a safe decision. Dirty working tree errors report a count instead of filenames. Error payloads must not include secrets, absolute local paths, raw private content, or untracked filenames.

The execution modules are tested to reject construction of the generic `CX_DEMO_CONTRACT_VIOLATION` code. New errors in `live.py`, `walkthrough.py`, or `acceptance.py` must select an explicit code and preserve the decision rules above.
