"""Реестр лицензий (мок external-mocks): действующие лицензии компании. Боевой реестр — другой
адаптер за тем же портом `LicenseSource`."""

from __future__ import annotations

from typing import Any

from src.modules.enrichment.application.dto.aml import LicenseDTO
from src.modules.enrichment.application.interfaces.sources import LicenseSource
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource

_ACTIVE = "ДЕЙСТВУЕТ"


class LicensesHttpSource(HttpSource, LicenseSource):
    async def fetch(self, inn: str) -> tuple[LicenseDTO, ...]:
        raw = await self._request("GET", f"/licenses/{inn}")
        try:
            return _map(raw)
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable(
                "bad_response", f"неожиданный ответ реестра лицензий: {exc}"
            ) from exc


def _map(raw: dict[str, Any]) -> tuple[LicenseDTO, ...]:
    """Только действующие: приостановленная или аннулированная лицензия — всё равно что нет."""
    return tuple(
        LicenseDTO(
            number=str(item["Номер"]),
            activity=str(item["ВидДеятельности"]),
            okved=str(item["ОКВЭД"]),
        )
        for item in raw["Лицензии"]
        if str(item["Статус"]) == _ACTIVE
    )
