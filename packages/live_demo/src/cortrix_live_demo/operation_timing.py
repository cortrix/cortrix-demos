"""Durable timing receipts for controller operations and business steps."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import time
import uuid
from typing import Any, Callable, Iterator


Record = Callable[[str, dict[str, Any]], None]
process_instance_id = uuid.uuid4().hex
_current_attempt_id: ContextVar[str | None] = ContextVar("current_timing_attempt_id", default=None)


def _terminal_status(error: BaseException) -> str:
    message = str(error).lower()
    error_name = error.__class__.__name__.lower()
    if "cancelled" in error_name or "canceled" in error_name or "demo_cancelled" in message or "cancelled" in message or "canceled" in message:
        return "cancelled"
    if error.__class__.__name__ == "Paused":
        return "paused"
    return "failed"


def safe_error_message(error: BaseException) -> str:
    """Keep stable error codes while excluding command text and runtime paths."""
    message = str(error)
    code = message.split(":", 1)[0]
    if code and len(code) <= 96 and all(character.isupper() or character.isdigit() or character == "_" for character in code):
        return code
    return "Operation failed; inspect private operator logs."


def current_timing_context() -> dict[str, str | None]:
    """Return receipt linkage metadata without exposing mutable context state."""
    return {
        "parent_attempt_id": _current_attempt_id.get(),
        "process_instance_id": process_instance_id,
    }


@contextmanager
def timed_attempt(
    record: Record,
    step_id: str,
    operation: str,
    owner: str,
    *,
    source: str = "business_step",
    event_prefix: str = "business_step",
    timing_scope: str = "step",
) -> Iterator[dict[str, Any]]:
    """Persist one started receipt and at most one terminal receipt."""
    attempt_id = uuid.uuid4().hex
    parent_attempt_id = _current_attempt_id.get()
    started = time.monotonic_ns()
    identity = {
        "schema_version": 2,
        "attempt_id": attempt_id,
        "parent_attempt_id": parent_attempt_id,
        "process_instance_id": process_instance_id,
        "step_id": step_id,
        "operation": operation,
        "owner": owner,
        "source": source,
        "timing_scope": timing_scope,
        "started_monotonic_ns": started,
    }
    record(event_prefix + "_started", {**identity, "status": "started", "state": "started"})
    token = _current_attempt_id.set(attempt_id)
    try:
        yield identity
    except BaseException as error:
        ended = time.monotonic_ns()
        status = _terminal_status(error)
        record(
            event_prefix + "_" + status,
            {
                **identity,
                "status": status,
                "state": status,
                "ended_monotonic_ns": ended,
                "duration_ns": ended - started,
                "duration_ms": (ended - started) / 1_000_000,
                "error_type": error.__class__.__name__,
                "error": safe_error_message(error),
            },
        )
        raise
    else:
        ended = time.monotonic_ns()
        record(
            event_prefix + "_completed",
            {
                **identity,
                "status": "completed",
                "state": "completed",
                "ended_monotonic_ns": ended,
                "duration_ns": ended - started,
                "duration_ms": (ended - started) / 1_000_000,
            },
        )
    finally:
        _current_attempt_id.reset(token)
