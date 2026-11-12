"""Errors and structured issues shared by cleaning and transformation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class DatasetDetectionError(ValueError):
    """Raised when automatic dataset detection is unsafe."""


class DatasetIOError(RuntimeError):
    """Raised for expected input/output format and filesystem errors."""


class PipelineValidationError(ValueError):
    """Raised by strict mode when a recoverable issue was found."""


@dataclass(frozen=True, slots=True)
class PipelineIssue:
    code: str
    message: str
    column: str | None = None
    row: int | str | None = None
    value: Any = None

    def format(self) -> str:
        location = []
        if self.column is not None:
            location.append(f"columna={self.column}")
        if self.row is not None:
            location.append(f"fila={self.row}")
        suffix = f" ({', '.join(location)})" if location else ""
        return f"{self.code}: {self.message}{suffix}"
