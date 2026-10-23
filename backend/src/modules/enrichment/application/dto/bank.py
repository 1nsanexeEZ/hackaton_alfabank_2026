"""Собственные данные банка (АБС): внутренний стоп-лист."""

# Без `from __future__ import annotations`: pydantic (ответы API на этих DTO) собирает схему по
# настоящим типам полей.
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class BankStopListDTO:
    """Компания во внутреннем стоп-листе банка или нет; причина — для банка, не для клиента."""

    listed: bool
    reason: str | None = None
    listed_at: date | None = None
