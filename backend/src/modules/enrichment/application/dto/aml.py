"""Проверка по 115-ФЗ на заявку: бенефициары, перечни Росфинмониторинга, ПДЛ, уровень ЗСК.

Делается заново на каждой заявке, в том числе у клиента, который уже получал кредит: перечни
обновляются ежедневно, владельцы и руководитель меняются, прошлый результат не переиспользуется.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

# terrorism — перечень причастных к экстремизму и терроризму; freeze — решение МВК
# о замораживании; wmd — перечень по распространению оружия массового уничтожения (ФРОМУ).
AmlList = Literal["terrorism", "freeze", "wmd"]
# foreign — иностранное ПДЛ, russian — российское, international — должностное лицо
# публичной международной организации (ст. 7.3 115-ФЗ).
PepKind = Literal["foreign", "russian", "international"]
# Уровень риска на платформе «Знай своего клиента» Банка России (ст. 7.6 115-ФЗ).
ZskLevel = Literal["low", "medium", "high"]
SubjectRole = Literal["company", "head", "beneficial_owner", "founder_company", "representative"]
# ownership — владеет больше 25% прямо или по цепочке; head_by_default — больше 25% нет ни у
# кого, бенефициаром признан руководитель; entrepreneur — ИП, бенефициар — он сам.
BeneficialOwnerBasis = Literal["ownership", "head_by_default", "entrepreneur"]


@dataclass(frozen=True, slots=True)
class AmlSubjectDTO:
    """Кого проверили: организацию — по ИНН, человека — по ФИО."""

    role: SubjectRole
    name: str
    inn: str | None = None


@dataclass(frozen=True, slots=True)
class BeneficialOwnerDTO:
    name: str
    basis: BeneficialOwnerBasis
    share_percent: Decimal | None = None  # итоговая доля, прямо и по цепочке; None — не по доле


@dataclass(frozen=True, slots=True)
class ListHitDTO:
    subject: AmlSubjectDTO
    list: AmlList
    record: str  # номер записи в перечне


@dataclass(frozen=True, slots=True)
class PepHitDTO:
    subject: AmlSubjectDTO
    kind: PepKind
    position: str


@dataclass(frozen=True, slots=True)
class ZskRiskDTO:
    level: ZskLevel
    as_of: date


@dataclass(frozen=True, slots=True)
class ListScreeningDTO:
    """Ответ перечней: совпадения по индексу проверяемого в запросе."""

    lists_date: date
    hits: tuple[tuple[int, AmlList, str], ...]


@dataclass(frozen=True, slots=True)
class PepScreeningDTO:
    hits: tuple[tuple[int, PepKind, str], ...]


@dataclass(frozen=True, slots=True)
class AmlCheckDTO:
    lists_date: date  # версия перечней, по которой проверили
    zsk: ZskRiskDTO
    beneficial_owners: tuple[BeneficialOwnerDTO, ...]
    subjects: tuple[AmlSubjectDTO, ...]
    list_hits: tuple[ListHitDTO, ...] = ()
    pep_hits: tuple[PepHitDTO, ...] = ()
