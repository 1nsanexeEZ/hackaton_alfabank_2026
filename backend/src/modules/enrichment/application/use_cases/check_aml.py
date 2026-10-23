"""Проверка по 115-ФЗ на заявку — заново на каждой, без кеша и без прошлых результатов.

1. Бенефициары: учредители из ЕГРЮЛ, по учредителям-юрлицам — их выписки по цепочке; доля
   больше 25% прямо или косвенно, никого — руководитель, у ИП — он сам (`domain.beneficial_owners`).
2. Перечни Росфинмониторинга (экстремизм и терроризм, решения МВК, ФРОМУ): компания и
   учредители-юрлица цепочки — по ИНН, руководитель, бенефициары и представитель — по ФИО.
3. ПДЛ (ст. 7.3): руководитель, бенефициары, представитель.
4. Уровень риска на платформе ЗСК Банка России (ст. 7.6).

Не установить цепочку, не ответил ЕГРЮЛ, перечни, база ПДЛ или ЗСК — проверка не выполнена
(`SourceFetchError`): заявка без проверки по 115-ФЗ автоматически не одобряется.
"""

from __future__ import annotations

import asyncio

from src.modules.enrichment.application.dto.aml import (
    AmlCheckDTO,
    AmlSubjectDTO,
    BeneficialOwnerDTO,
    ListHitDTO,
    PepHitDTO,
)
from src.modules.enrichment.application.dto.registry import FounderDTO, RegistryExtractDTO
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.domain.beneficial_owners import (
    MAX_DEPTH,
    BeneficialOwner,
    OwnershipUnresolved,
    Stake,
    beneficial_owners,
    person_shares,
)
from src.modules.enrichment.domain.exceptions import SourceFetchError, SourceNotFound

_ENTREPRENEUR = "ИП"


class AmlCheck:
    def __init__(self, sources: Sources) -> None:
        self._sources = sources

    async def run(
        self, registry: RegistryExtractDTO | None, *, representatives: tuple[str, ...] = ()
    ) -> AmlCheckDTO:
        """`registry` — выписка ЕГРЮЛ этой заявки; `representatives` — ФИО тех, кто действует
        от имени клиента (подал заявку), кроме руководителя."""
        if registry is None:
            raise SourceFetchError(
                "incomplete", "ЕГРЮЛ не ответил — не установить руководителя и бенефициаров"
            )
        chain = await self._chain(registry)
        head = _head(registry)
        try:
            shares = person_shares(_stakes(registry.founders), _chain_stakes(chain))
        except OwnershipUnresolved as exc:
            raise SourceFetchError("incomplete", f"бенефициаров не установить: {exc}") from exc
        owners = beneficial_owners(
            shares, head=head, entrepreneur=registry.legal_form == _ENTREPRENEUR
        )

        subjects = _subjects(registry, chain, head, owners, representatives)
        people = tuple(dict.fromkeys(s.name for s in subjects if s.inn is None))
        lists, pep, zsk = await asyncio.gather(
            self._sources.aml_lists.screen(subjects),
            self._sources.pep.screen(people),
            self._sources.zsk.fetch(registry.inn),
        )
        return AmlCheckDTO(
            lists_date=lists.lists_date,
            zsk=zsk,
            beneficial_owners=tuple(
                BeneficialOwnerDTO(o.name, o.basis, o.share_percent) for o in owners
            ),
            subjects=subjects,
            list_hits=tuple(
                ListHitDTO(subjects[index], kind, record) for index, kind, record in lists.hits
            ),
            pep_hits=tuple(
                PepHitDTO(subject, kind, position)
                for index, kind, position in pep.hits
                for subject in subjects
                if subject.inn is None and subject.name == people[index]
            ),
        )

    async def _chain(self, registry: RegistryExtractDTO) -> dict[str, RegistryExtractDTO]:
        """Выписки учредителей-юрлиц по цепочке владения, по ИНН."""
        found: dict[str, RegistryExtractDTO] = {}
        level = [f.inn for f in registry.founders if f.inn is not None]
        for _ in range(MAX_DEPTH):
            pending = [inn for inn in dict.fromkeys(level) if inn not in found]
            if not pending:
                break
            for extract in await asyncio.gather(*(self._extract(inn) for inn in pending)):
                found[extract.inn] = extract
            level = [f.inn for inn in pending for f in found[inn].founders if f.inn is not None]
        return found

    async def _extract(self, inn: str) -> RegistryExtractDTO:
        try:
            return await self._sources.registry.fetch(inn)
        except SourceNotFound as exc:
            raise SourceFetchError(
                "incomplete", f"учредитель-юрлицо ИНН {inn} не найден в ЕГРЮЛ"
            ) from exc


def _chain_stakes(chain: dict[str, RegistryExtractDTO]) -> dict[str, tuple[Stake, ...]]:
    return {inn: _stakes(extract.founders) for inn, extract in chain.items()}


def _stakes(founders: tuple[FounderDTO, ...]) -> tuple[Stake, ...]:
    return tuple(Stake(f.name, f.share_percent, f.inn) for f in founders)


def _head(registry: RegistryExtractDTO) -> str:
    parts = (registry.head_last_name, registry.head_first_name, registry.head_middle_name)
    return " ".join(part for part in parts if part)


def _subjects(
    registry: RegistryExtractDTO,
    chain: dict[str, RegistryExtractDTO],
    head: str,
    owners: tuple[BeneficialOwner, ...],
    representatives: tuple[str, ...],
) -> tuple[AmlSubjectDTO, ...]:
    subjects = [
        AmlSubjectDTO("company", registry.full_name, registry.inn),
        *(AmlSubjectDTO("founder_company", e.full_name, e.inn) for e in chain.values()),
        AmlSubjectDTO("head", head),
        *(AmlSubjectDTO("beneficial_owner", o.name) for o in owners if o.name != head),
        *(AmlSubjectDTO("representative", name) for name in representatives if name != head),
    ]
    return tuple(dict.fromkeys(subjects))
