import re
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from src.core.exceptions.exceptions import ValidationError

SUBJECT_MAX_LENGTH = 200
TEXT_MAX_LENGTH = 4000


@dataclass(frozen=True, slots=True)
class TicketNumber:
    """`ТП-2026-000123`: year of creation and a database sequence value."""

    value: str

    _PATTERN = re.compile(r"^ТП-\d{4}-\d{6}$")

    def __post_init__(self) -> None:
        if not self._PATTERN.match(self.value):
            raise ValueError(f"Invalid ticket number {self.value!r}")

    @classmethod
    def issue(cls, year: int, sequence: int) -> Self:
        if not 0 < sequence < 1_000_000:
            raise ValueError("Ticket number sequence is exhausted")
        return cls(f"ТП-{year:04d}-{sequence:06d}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Staff:
    """A bank employee acting on the queue. A supervisor (the admin) may answer,
    resolve, close and return to the queue a ticket taken by someone else."""

    account_id: UUID
    supervisor: bool = False


def clean_text(value: str, field: str, max_length: int) -> str:
    """Text of a subject or a message: not blank, not longer than the limit.
    HTML is already stripped by the API schema."""
    text = value.strip()
    if not text:
        raise ValidationError(f"{field} is empty", details={"field": field})
    if len(text) > max_length:
        raise ValidationError(
            f"{field} is longer than {max_length} characters",
            details={"field": field, "max_length": max_length},
        )
    return text
