from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.modules.enrichment.application.dto.registry import FounderDTO, RegistryExtractDTO
from src.modules.enrichment.application.interfaces.sources import RegistrySource
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource

_STATUS = {
    "ACTIVE": "active",
    "LIQUIDATING": "liquidating",
    "LIQUIDATED": "liquidated",
    "BANKRUPT": "bankrupt",
    "REORGANIZING": "reorganizing",
    "EXCLUDED": "excluded",
}
# Записи о недостоверности сведений: что именно признано недостоверным.
_UNRELIABLE = {"Адрес": "address", "Руководитель": "head", "Учредитель": "founder"}


class EgrulHttpSource(HttpSource, RegistrySource):
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
    head_since = raw["Руководитель"].get("ДатаЗаписи")
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
        founders=tuple(_founder(f) for f in raw.get("Учредители", [])),
        address=str(raw["Адрес"]["Полный"]),
        region_code=str(raw["Адрес"]["КодРегиона"]),
        mass_address=bool(raw["МассовыйАдрес"]),
        kpp=str(raw["КПП"]) if raw.get("КПП") else None,
        head_since=date.fromisoformat(head_since) if head_since else None,
        unreliable=tuple(
            dict.fromkeys(_UNRELIABLE[str(r["Сведения"])] for r in raw.get("СведНедостоверн", []))
        ),
    )


def _founder(raw: dict[str, Any]) -> FounderDTO:
    """Физлицо — `ФИО`; юрлицо — `Наим` и `ИНН`."""
    share = Decimal(str(raw["Доля"]))
    country = _country(raw.get("Страна"))
    if "ИНН" in raw:
        return FounderDTO(
            name=str(raw["Наим"]), share_percent=share, inn=str(raw["ИНН"]), country=country
        )
    return FounderDTO(name=str(raw["ФИО"]), share_percent=share, country=country)


def _country(raw: Any) -> str | None:
    """Код страны ISO 3166-1 alpha-2; Россия и пусто — None."""
    if raw is None:
        return None
    code = str(raw).upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError(f"неизвестный код страны {raw!r}")
    return None if code == "RU" else code
