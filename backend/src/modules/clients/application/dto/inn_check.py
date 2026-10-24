"""Check of a company by INN before an application: what the bank employee asks and sees."""

# No `from __future__ import annotations`: the `date: date` fields would point at themselves,
# and pydantic would not build the response schema.
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from src.modules.clients.application.dto.organizations import AddressDTO
from src.modules.clients.domain.inn_check import (
    Check,
    CompanyRecord,
    CourtRecord,
    InnCheck,
    RegistryRecord,
    TaxRecord,
)


@dataclass(frozen=True, slots=True)
class InnCheckRequestDTO:
    """`ogrn`, `kpp`, `name` — from the client's documents: the INN is matched against them."""

    inn: str
    ogrn: str | None = None
    kpp: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class CheckDTO:
    code: str
    title: str
    # passed | warning | failed | skipped
    status: str
    message: str
    # input | egrul | fns | kontur | bank
    source: str


@dataclass(frozen=True, slots=True)
class FounderDTO:
    name: str
    share_percent: Decimal
    inn: str | None


@dataclass(frozen=True, slots=True)
class RegistryCompanyDTO:
    """ЕГРЮЛ/ЕГРИП: the name is short (`ООО «Ромашка»`), the full one is next to it."""

    inn: str
    ogrn: str
    kpp: str | None
    legal_form: str
    name: str
    full_name: str
    registry_status: str
    registered_at: date
    address: AddressDTO
    mass_address: bool
    # Records of unreliable data: address | head | founder.
    unreliable: tuple[str, ...]
    okved_main: str
    okved_extra: tuple[str, ...]
    head_name: str
    head_position: str
    head_since: date | None
    founders: tuple[FounderDTO, ...]

    @classmethod
    def of(cls, registry: RegistryRecord) -> Self:
        extract = registry.extract
        return cls(
            inn=extract.inn.value,
            ogrn=extract.ogrn.value,
            kpp=extract.kpp.value if extract.kpp else None,
            legal_form=registry.legal_form.value,
            name=extract.name,
            full_name=registry.full_name,
            registry_status=extract.status.value,
            registered_at=registry.registered_at,
            address=AddressDTO(full=extract.address.full, region_code=extract.address.region_code),
            mass_address=registry.mass_address,
            unreliable=registry.unreliable,
            okved_main=extract.okved_main.value,
            okved_extra=tuple(code.value for code in extract.okved_extra),
            head_name=extract.head.full,
            head_position=registry.head_position,
            head_since=registry.head_since,
            founders=tuple(FounderDTO(f.name, f.share_percent, f.inn) for f in registry.founders),
        )


@dataclass(frozen=True, slots=True)
class AccountBlockDTO:
    decision_number: str
    date: date
    reason: str


@dataclass(frozen=True, slots=True)
class TaxDTO:
    """The tax service («Прозрачный бизнес»), rubles."""

    tax_regime: str
    avg_headcount: int
    reported_revenue: Decimal | None
    report_year: int | None
    tax_arrears: Decimal
    in_msp_registry: bool
    disqualified_head: bool
    mass_head: bool | None
    account_blocks: tuple[AccountBlockDTO, ...]

    @classmethod
    def of(cls, tax: TaxRecord) -> Self:
        return cls(
            tax_regime=tax.tax_regime,
            avg_headcount=tax.avg_headcount,
            reported_revenue=tax.reported_revenue,
            report_year=tax.report_year,
            tax_arrears=tax.tax_arrears,
            in_msp_registry=tax.in_msp_registry,
            disqualified_head=tax.disqualified_head,
            mass_head=tax.mass_head,
            account_blocks=tuple(
                AccountBlockDTO(b.decision_number, b.date, b.reason) for b in tax.account_blocks
            ),
        )


@dataclass(frozen=True, slots=True)
class BankruptcyMessageDTO:
    date: date
    type: str
    case: str


@dataclass(frozen=True, slots=True)
class CounterpartyDTO:
    """Kontur: courts, bailiffs, bankruptcy; rubles."""

    reliability: str
    notes: tuple[str, ...]
    arbitration_as_defendant: int
    arbitration_defendant_sum: Decimal
    enforcement_active: int
    enforcement_sum: Decimal
    bankruptcy_messages: tuple[BankruptcyMessageDTO, ...]

    @classmethod
    def of(cls, court: CourtRecord) -> Self:
        return cls(
            reliability=court.reliability,
            notes=court.notes,
            arbitration_as_defendant=court.arbitration_as_defendant,
            arbitration_defendant_sum=court.arbitration_defendant_sum,
            enforcement_active=court.enforcement_active,
            enforcement_sum=court.enforcement_sum,
            bankruptcy_messages=tuple(
                BankruptcyMessageDTO(n.date, n.kind, n.case) for n in court.bankruptcy
            ),
        )


@dataclass(frozen=True, slots=True)
class InnCheckDTO:
    inn: str
    # ok | warning | fail | not_found
    verdict: str
    summary: str
    checked_at: datetime
    checks: tuple[CheckDTO, ...]
    # None — nothing found: an unknown INN or a typo in it.
    company: RegistryCompanyDTO | None
    # None — the source did not answer (or nothing found).
    tax: TaxDTO | None
    counterparty: CounterpartyDTO | None
    # The company is a client of the bank: its card.
    organization_id: UUID | None

    @classmethod
    def of(cls, result: InnCheck, now: datetime, organization_id: UUID | None = None) -> Self:
        record: CompanyRecord | None = result.record
        return cls(
            inn=result.inn,
            verdict=result.verdict.value,
            summary=result.summary,
            checked_at=now,
            checks=tuple(_check(c) for c in result.checks),
            company=RegistryCompanyDTO.of(record.registry) if record else None,
            tax=TaxDTO.of(record.tax) if record and record.tax else None,
            counterparty=CounterpartyDTO.of(record.court) if record and record.court else None,
            organization_id=organization_id,
        )


def _check(check: Check) -> CheckDTO:
    return CheckDTO(
        code=check.code,
        title=check.title,
        status=check.status.value,
        message=check.message,
        source=check.source.value,
    )
