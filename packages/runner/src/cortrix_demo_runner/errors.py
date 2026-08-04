from __future__ import annotations

from typing import Any


class DemoContractError(RuntimeError):
    """Raised when a fail-closed demo contract is not satisfied."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "CX_DEMO_CONTRACT_VIOLATION",
        category: str = "permanent",
        retryable: bool = False,
        structured_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category
        self.retryable = retryable
        self.structured_data = structured_data or {}

    def as_dict(self, message: str | None = None) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "category": self.category,
                "retryable": self.retryable,
                "message": str(self) if message is None else message,
                "structured_data": self.structured_data,
            }
        }
