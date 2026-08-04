from __future__ import annotations

from typing import Any


ERROR_CATEGORIES = {"auth", "quota", "transient", "permanent", "timeout"}


class DemoContractError(RuntimeError):
    """Raised when a fail-closed demo contract is not satisfied."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "CX_DEMO_CONTRACT_VIOLATION",
        category: str = "permanent",
        retryable: bool = False,
        retry_after_ms: int | None = None,
        structured_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if category not in ERROR_CATEGORIES:
            raise ValueError(f"Unsupported error category: {category}")
        if retryable and (not isinstance(retry_after_ms, int) or retry_after_ms < 0):
            raise ValueError("Retryable errors must provide a non-negative retry_after_ms value")
        if not retryable and retry_after_ms is not None:
            raise ValueError("Non-retryable errors must not provide retry_after_ms")
        self.code = code
        self.category = category
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms
        self.structured_data = structured_data or {}

    def as_dict(self, message: str | None = None) -> dict[str, Any]:
        error = {
            "code": self.code,
            "category": self.category,
            "retryable": self.retryable,
            "message": str(self) if message is None else message,
            "structured_data": self.structured_data,
        }
        if self.retry_after_ms is not None:
            error["retry_after_ms"] = self.retry_after_ms
        return {"error": error}
