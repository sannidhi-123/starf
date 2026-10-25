"""Custom exceptions for STARK."""

from __future__ import annotations


class StarkError(Exception):
    """Base exception for all STARK errors."""


class SchemaValidationError(StarkError):
    """Raised when DataFrame schema or content validation fails.

    Attributes:
        message: Descriptive error message.
        column: Column name that triggered the validation failure.
        row: 0-indexed row position of the first invalid entry.
    """

    def __init__(
        self,
        message: str,
        column: str | None = None,
        row: int | None = None,
    ) -> None:
        """Initialize SchemaValidationError.

        Args:
            message: Descriptive error message.
            column: Name of the invalid column (if applicable).
            row: 0-indexed row position of the first failure (if applicable).
        """
        self.message = message
        self.column = column
        self.row = row
        details: list[str] = []
        if column is not None:
            details.append(f"column='{column}'")
        if row is not None:
            details.append(f"row={row}")
        full_message = f"{message} ({', '.join(details)})" if details else message
        super().__init__(full_message)


class DatasetFormatError(StarkError):
    """Raised when raw dataset file parsing fails or format is unrecognized."""
