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
# beneficiary — выгодоприобретатель, к выгоде которого действует клиент; pledgor — владелец
# залога, если это не клиент. Оба — со слов клиента в заявке. founder — учредитель-физлицо с
# любой долей (ст. 7 п. 10, 14); declared_owner — бенефициар со слов клиента, которого нет среди
# остальных проверяемых (например, контролирует компанию без доли).
SubjectRole = Literal[
    "company",
    "head",
    "beneficial_owner",
    "founder_company",
    "representative",
    "beneficiary",
    "pledgor",
    "founder",
    "declared_owner",
]
# ownership — владеет больше 25% прямо или по цепочке; head_by_default — больше 25% нет ни у
# кого, бенефициаром признан руководитель; entrepreneur — ИП, бенефициар — он сам.
BeneficialOwnerBasis = Literal["ownership", "head_by_default", "entrepreneur"]
# Со слов клиента (ст. 6.1, ст. 7 п. 14): ownership — владеет больше 25%; control — иначе
# контролирует действия компании (ст. 3).
DeclaredOwnerBasis = Literal["ownership", "control"]
# not_declared — бенефициар по ЕГРЮЛ, которого клиент не назвал; not_in_registry — клиент назвал
# владельца больше 25%, а по ЕГРЮЛ его нет.
OwnerDiscrepancyKind = Literal["not_declared", "not_in_registry"]


@dataclass(frozen=True, slots=True)
class AmlSubjectDTO:
    """Кого проверили: организацию — по ИНН, человека — по ФИО."""

    role: SubjectRole
    name: str
    inn: str | None = None
    # Страна регистрации или места жительства (ISO 3166-1 alpha-2), если не Россия; None —
    # Россия или не указана.
    country: str | None = None


@dataclass(frozen=True, slots=True)
class BeneficialOwnerDTO:
    name: str
    basis: BeneficialOwnerBasis
    share_percent: Decimal | None = None  # итоговая доля, прямо и по цепочке; None — не по доле


@dataclass(frozen=True, slots=True)
class DeclaredOwnerDTO:
    """Бенефициар со слов клиента."""

    name: str
    basis: DeclaredOwnerBasis
    country: str | None = None


@dataclass(frozen=True, slots=True)
class OwnerDiscrepancyDTO:
    name: str
    kind: OwnerDiscrepancyKind


@dataclass(frozen=True, slots=True)
class LicenseDTO:
    """Действующая лицензия из реестра лицензий (ст. 7 п. 15 115-ФЗ)."""

    number: str
    activity: str  # вид деятельности по лицензии
    okved: str  # код ОКВЭД, на который выдана


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
    # Бенефициары со слов клиента; None — клиент не ответил (или снимок до вопроса).
    declared_owners: tuple[DeclaredOwnerDTO, ...] | None = None
    # Расхождения названных клиентом бенефициаров с ЕГРЮЛ; только если клиент ответил.
    owner_discrepancies: tuple[OwnerDiscrepancyDTO, ...] = ()
    # Действующие лицензии компании; None — реестр не запрашивался (снимки до policy_v9).
    licenses: tuple[LicenseDTO, ...] | None = None
