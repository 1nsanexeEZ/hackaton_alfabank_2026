from __future__ import annotations

from datetime import date
from typing import Any

from src.modules.enrichment.application.dto.bank import BankStopListDTO
from src.modules.enrichment.application.interfaces.sources import BankStopListSource
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource


class BankStopListHttpSource(HttpSource, BankStopListSource):
    """Внутренний стоп-лист банка в АБС (мок external-mocks). Боевая АБС — другой адаптер за тем
    же портом `BankStopListSource`."""

    async def fetch(self, inn: str) -> BankStopListDTO:
        raw = await self._request("GET", f"/abs/stop-list/{inn}")
        try:
            return _map(raw)
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ стоп-листа: {exc}") from exc


def _map(raw: dict[str, Any]) -> BankStopListDTO:
    listed = raw["listed"]
    if not isinstance(listed, bool):
        raise ValueError(f"listed должен быть bool, пришло {listed!r}")
    listed_at = raw.get("listed_at")
    return BankStopListDTO(
        listed=listed,
        reason=str(raw["reason"]) if raw.get("reason") else None,
        listed_at=date.fromisoformat(listed_at) if listed_at else None,
    )
