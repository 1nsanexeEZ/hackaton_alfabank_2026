from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.modules.enrichment.application.ports import SourceUnavailable
from src.modules.enrichment.facade import FounderDTO, RegistryExtractDTO
from src.modules.enrichment.infrastructure.adapters.base import HttpSource

_STATUS = {
    "ACTIVE": "active",
    "LIQUIDATING": "liquidating",
    "LIQUIDATED": "liquidated",
    "BANKRUPT": "bankrupt",
}


class EgrulHttpSource(HttpSource):
    async def fetch(self, inn: str) -> RegistryExtractDTO:
        raw = await self._request("GET", f"/egrul/{inn}")
        try:
            return _map(raw)
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ ЕГРЮЛ: {exc}") from exc


def _map(raw: dict[str, Any]) -> RegistryExtractDTO:
    status = _STATUS.get(raw["Статус"]["Код"])
    if status is None:
        raise ValueError(f"неизвестный статус {raw['Статус']['Код']!r}")
    parts = str(raw["Руководитель"]["ФИО"]).split()
    return RegistryExtractDTO(
        inn=str(raw["ИНН"]),
        ogrn=str(raw["ОГРН"]),
        legal_form=str(raw["ОрганизационнаяФорма"]),
        full_name=str(raw["НаимПолн"]),
        status=status,
        registered_at=date.fromisoformat(raw["ДатаРег"]),
        okved_main=str(raw["ОКВЭДОсн"]["Код"]),
        okved_extra=tuple(str(item["Код"]) for item in raw.get("ОКВЭДДоп", [])),
        head_last_name=parts[0] if parts else "",
        head_first_name=parts[1] if len(parts) > 1 else "",
        head_middle_name=parts[2] if len(parts) > 2 else None,
        head_position=str(raw["Руководитель"]["Должность"]),
        founders=tuple(
            FounderDTO(name=str(f["ФИО"]), share_percent=Decimal(str(f["Доля"])))
            for f in raw.get("Учредители", [])
        ),
        address=str(raw["Адрес"]["Полный"]),
        region_code=str(raw["Адрес"]["КодРегиона"]),
        mass_address=bool(raw["МассовыйАдрес"]),
        kpp=str(raw["КПП"]) if raw.get("КПП") else None,
    )
