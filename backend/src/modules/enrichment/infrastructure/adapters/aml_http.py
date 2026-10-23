"""Адаптеры проверок по 115-ФЗ: перечни Росфинмониторинга, база ПДЛ, платформа ЗСК.

У каждой системы свой формат (ключи кириллицей, коды перечней строками) — здесь он переводится
в наши DTO. Неизвестный код перечня, категории ПДЛ или уровня ЗСК — `bad_response`: лучше
проверка «не выполнена», чем молча пропущенное совпадение.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from src.modules.enrichment.application.dto.aml import (
    AmlList,
    AmlSubjectDTO,
    ListScreeningDTO,
    PepKind,
    PepScreeningDTO,
    ZskLevel,
    ZskRiskDTO,
)
from src.modules.enrichment.application.interfaces.sources import (
    AmlListsSource,
    PepSource,
    ZskSource,
)
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource

_LISTS: dict[str, AmlList] = {
    "ЭКСТРЕМИЗМ_ТЕРРОРИЗМ": "terrorism",
    "МВК": "freeze",
    "ФРОМУ": "wmd",
}
_PEP: dict[str, PepKind] = {"ИПДЛ": "foreign", "РПДЛ": "russian", "МПДЛ": "international"}
_ZSK: dict[str, ZskLevel] = {"НИЗКИЙ": "low", "СРЕДНИЙ": "medium", "ВЫСОКИЙ": "high"}


class RfmHttpSource(HttpSource, AmlListsSource):
    """Перечни Росфинмониторинга: организация — по ИНН, физлицо — по ФИО."""

    async def screen(self, subjects: tuple[AmlSubjectDTO, ...]) -> ListScreeningDTO:
        body = {
            "request_id": str(uuid4()),
            "subjects": [
                {
                    "id": str(index),
                    "type": "UL" if subject.inn is not None else "FL",
                    "name": subject.name,
                    "inn": subject.inn,
                }
                for index, subject in enumerate(subjects)
            ],
        }
        raw = await self._request("POST", "/rfm/screen", json=body)
        try:
            return _map_lists(raw, len(subjects))
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ перечней: {exc}") from exc


class PepHttpSource(HttpSource, PepSource):
    async def screen(self, names: tuple[str, ...]) -> PepScreeningDTO:
        body = {
            "request_id": str(uuid4()),
            "persons": [{"id": str(index), "fio": name} for index, name in enumerate(names)],
        }
        raw = await self._request("POST", "/pep/screen", json=body)
        try:
            return _map_pep(raw, len(names))
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ базы ПДЛ: {exc}") from exc


class ZskHttpSource(HttpSource, ZskSource):
    async def fetch(self, inn: str) -> ZskRiskDTO:
        raw = await self._request("GET", f"/zsk/{inn}")
        try:
            return ZskRiskDTO(
                level=_ZSK[str(raw["Уровень"])],
                as_of=date.fromisoformat(raw["ДатаАктуальности"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ ЗСК: {exc}") from exc


def _index(raw: Any, count: int) -> int:
    index = int(raw)
    if not 0 <= index < count:
        raise ValueError(f"нет проверяемого с id {raw!r}")
    return index


def _map_lists(raw: dict[str, Any], count: int) -> ListScreeningDTO:
    results = raw["Результаты"]
    if len(results) != count:
        raise ValueError(f"ответ на {len(results)} из {count} проверяемых")
    return ListScreeningDTO(
        lists_date=date.fromisoformat(raw["ДатаАктуальности"]),
        hits=tuple(
            (_index(result["id"], count), _LISTS[str(hit["Перечень"])], str(hit["НомерЗаписи"]))
            for result in results
            for hit in result["Совпадения"]
        ),
    )


def _map_pep(raw: dict[str, Any], count: int) -> PepScreeningDTO:
    results = raw["Результаты"]
    if len(results) != count:
        raise ValueError(f"ответ на {len(results)} из {count} проверяемых")
    return PepScreeningDTO(
        hits=tuple(
            (_index(result["id"], count), _PEP[str(pep["Категория"])], str(pep["Должность"]))
            for result in results
            if (pep := result["ПДЛ"]) is not None
        )
    )
