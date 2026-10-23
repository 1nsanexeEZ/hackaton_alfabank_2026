"""Фейки проверок по 115-ФЗ: перечни Росфинмониторинга, база ПДЛ, платформа ЗСК.

По умолчанию все чистые; `listed` / `pep` — кто в перечне или ПДЛ (по ФИО или ИНН),
`fail` — источник не отвечает. `calls` — кого спрашивали: проверка идёт на каждой заявке.
"""

from __future__ import annotations

from datetime import date

from src.modules.enrichment.application.dto.aml import (
    AmlList,
    AmlSubjectDTO,
    ListScreeningDTO,
    PepKind,
    PepScreeningDTO,
    ZskLevel,
    ZskRiskDTO,
)
from src.modules.enrichment.domain.exceptions import SourceUnavailable

LISTS_DATE = date(2026, 10, 21)


class FakeAmlLists:
    def __init__(self, listed: dict[str, AmlList] | None = None, *, fail: bool = False) -> None:
        self.listed = listed or {}
        self.fail = fail
        self.calls: list[tuple[AmlSubjectDTO, ...]] = []

    async def screen(self, subjects: tuple[AmlSubjectDTO, ...]) -> ListScreeningDTO:
        self.calls.append(subjects)
        if self.fail:
            raise SourceUnavailable("unavailable", "перечни недоступны")
        hits = tuple(
            (index, kind, f"REC-{index}")
            for index, subject in enumerate(subjects)
            if (kind := self.listed.get(subject.inn or subject.name)) is not None
        )
        return ListScreeningDTO(lists_date=LISTS_DATE, hits=hits)


class FakePep:
    def __init__(self, pep: dict[str, PepKind] | None = None, *, fail: bool = False) -> None:
        self.pep = pep or {}
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    async def screen(self, names: tuple[str, ...]) -> PepScreeningDTO:
        self.calls.append(names)
        if self.fail:
            raise SourceUnavailable("unavailable", "база ПДЛ недоступна")
        return PepScreeningDTO(
            hits=tuple(
                (index, kind, "Должность")
                for index, name in enumerate(names)
                if (kind := self.pep.get(name)) is not None
            )
        )


class FakeZsk:
    def __init__(self, level: ZskLevel = "low", *, fail: bool = False) -> None:
        self.level: ZskLevel = level
        self.fail = fail
        self.calls: list[str] = []

    async def fetch(self, inn: str) -> ZskRiskDTO:
        self.calls.append(inn)
        if self.fail:
            raise SourceUnavailable("unavailable", "ЗСК недоступна")
        return ZskRiskDTO(level=self.level, as_of=LISTS_DATE)
