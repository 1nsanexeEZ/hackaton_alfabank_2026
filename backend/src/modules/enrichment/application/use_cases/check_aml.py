"""Проверка по 115-ФЗ на заявку — заново на каждой, без кеша и без прошлых результатов.

1. Бенефициары: учредители из ЕГРЮЛ, по учредителям-юрлицам — их выписки по цепочке; доля
   больше 25% прямо или косвенно, никого — руководитель, у ИП — он сам (`domain.beneficial_owners`).
2. Перечни Росфинмониторинга (экстремизм и терроризм, решения МВК, ФРОМУ): компания и
   учредители-юрлица цепочки — по ИНН, руководитель, бенефициары, учредители-физлица с любой
   долей (ст. 7 п. 10, 14) и представитель — по ФИО; выгодоприобретатель, залогодатель и
   бенефициары со слов клиента — организация по ИНН, человек по ФИО.
3. ПДЛ (ст. 7.3): все проверяемые физлица.
4. Уровень риска на платформе ЗСК Банка России (ст. 7.6).
5. Бенефициары со слов клиента (ст. 6.1, ст. 7 п. 14) сверяются с ЕГРЮЛ: кого клиент не назвал
   и кого назвал владельцем, а по реестру его нет.
6. Действующие лицензии из реестра лицензий (ст. 7 п. 15): нужна ли лицензия, решает decision.

У каждого проверяемого — страна, если не Россия (учредители — по ЕГРЮЛ, остальные — со слов
клиента): участник из государства, не выполняющего рекомендации ФАТФ, — фактор группы риска.

Не установить цепочку, не ответил ЕГРЮЛ, перечни, база ПДЛ, ЗСК или реестр лицензий — проверка не
выполнена (`SourceFetchError`): заявка без проверки по 115-ФЗ автоматически не одобряется.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from src.modules.enrichment.application.dto.aml import (
    AmlCheckDTO,
    AmlSubjectDTO,
    BeneficialOwnerDTO,
    DeclaredOwnerDTO,
    ListHitDTO,
    OwnerDiscrepancyDTO,
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
        self,
        registry: RegistryExtractDTO | None,
        *,
        representatives: tuple[str, ...] = (),
        third_parties: tuple[AmlSubjectDTO, ...] = (),
        declared_owners: tuple[DeclaredOwnerDTO, ...] | None = None,
    ) -> AmlCheckDTO:
        """`registry` — выписка ЕГРЮЛ этой заявки; `representatives` — ФИО тех, кто действует
        от имени клиента (подал заявку), кроме руководителя; `third_parties` —
        выгодоприобретатель и залогодатель, которых клиент указал в заявке; `declared_owners` —
        бенефициары со слов клиента, None — клиент не ответил."""
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

        subjects = _subjects(registry, chain, head, owners, shares, representatives)
        subjects += tuple(p for p in dict.fromkeys(third_parties) if p not in subjects)
        subjects += _declared_subjects(subjects, declared_owners)
        people = tuple(dict.fromkeys(s.name for s in subjects if s.inn is None))
        lists, pep, zsk, licenses = await asyncio.gather(
            self._sources.aml_lists.screen(subjects),
            self._sources.pep.screen(people),
            self._sources.zsk.fetch(registry.inn),
            self._sources.licenses.fetch(registry.inn),
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
            declared_owners=declared_owners,
            owner_discrepancies=_discrepancies(owners, declared_owners),
            licenses=licenses,
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
    shares: dict[str, Decimal],
    representatives: tuple[str, ...],
) -> tuple[AmlSubjectDTO, ...]:
    """Компания, цепочка, руководитель, бенефициары, остальные учредители-физлица (с любой
    долей), представитель. Страна — по ЕГРЮЛ: у учредителей она указана в выписке."""
    countries = _countries(registry, chain)
    owner_names = {o.name for o in owners}
    country = countries.get
    subjects = [
        AmlSubjectDTO("company", registry.full_name, registry.inn),
        *(
            AmlSubjectDTO("founder_company", e.full_name, e.inn, country(e.inn))
            for e in chain.values()
        ),
        AmlSubjectDTO("head", head, country=country(head)),
        *(
            AmlSubjectDTO("beneficial_owner", o.name, country=country(o.name))
            for o in owners
            if o.name != head
        ),
        *(
            AmlSubjectDTO("founder", name, country=country(name))
            for name in shares
            if name != head and name not in owner_names
        ),
        *(AmlSubjectDTO("representative", name) for name in representatives if name != head),
    ]
    return tuple(dict.fromkeys(subjects))


def _countries(
    registry: RegistryExtractDTO, chain: dict[str, RegistryExtractDTO]
) -> dict[str, str]:
    """Страна учредителя по выписке: физлицо — по ФИО, юрлицо — по ИНН."""
    founders = (*registry.founders, *(f for e in chain.values() for f in e.founders))
    return {f.inn or f.name: f.country for f in founders if f.country is not None}


def _declared_subjects(
    subjects: tuple[AmlSubjectDTO, ...], declared: tuple[DeclaredOwnerDTO, ...] | None
) -> tuple[AmlSubjectDTO, ...]:
    """Бенефициары со слов клиента, которых ещё нет среди проверяемых физлиц."""
    known = {_normalize(s.name) for s in subjects if s.inn is None}
    return tuple(
        dict.fromkeys(
            AmlSubjectDTO("declared_owner", owner.name, country=owner.country)
            for owner in declared or ()
            if _normalize(owner.name) not in known
        )
    )


def _discrepancies(
    owners: tuple[BeneficialOwner, ...], declared: tuple[DeclaredOwnerDTO, ...] | None
) -> tuple[OwnerDiscrepancyDTO, ...]:
    """Бенефициары по доле (ЕГРЮЛ), которых клиент не назвал, и названные владельцами больше
    25%, которых по ЕГРЮЛ нет. Контроль без доли в реестре не виден — с ним не сверяем. Клиент
    не ответил или это ИП — сверять не с чем."""
    if declared is None or any(o.basis == "entrepreneur" for o in owners):
        return ()
    registry = {_normalize(o.name): o.name for o in owners if o.basis == "ownership"}
    named = {_normalize(o.name) for o in declared}
    by_share = {_normalize(o.name): o.name for o in declared if o.basis == "ownership"}
    return (
        *(
            OwnerDiscrepancyDTO(name, "not_declared")
            for key, name in registry.items()
            if key not in named
        ),
        *(
            OwnerDiscrepancyDTO(name, "not_in_registry")
            for key, name in by_share.items()
            if key not in registry
        ),
    )


def _normalize(name: str) -> str:
    """Сверка ФИО: регистр, «ё», лишние пробелы."""
    return " ".join(name.lower().replace("ё", "е").split())
