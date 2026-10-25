from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.types import SafeString
from src.modules.clients.application.dto.inn_check import InnCheckRequestDTO
from src.modules.clients.presentation.schemas.organizations import AddressRead, LegalForm


class InnCheckRequest(BaseModel):
    """The INN and, if the client named them, the requisites from their documents: the INN is
    matched against each one passed."""

    inn: str = Field(
        pattern=r"^([0-9]{10}|[0-9]{12})$",
        description="10 digits — a legal entity, 12 — an entrepreneur",
    )
    ogrn: str | None = Field(
        default=None, pattern=r"^([0-9]{13}|[0-9]{15})$", description="ОГРН or ОГРНИП"
    )
    kpp: str | None = Field(default=None, pattern=r"^[0-9]{4}[0-9A-Z]{2}[0-9]{3}$")
    name: SafeString | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="With or without the legal form: `ООО «Ромашка»`, `Ромашка`",
    )

    def to_dto(self) -> InnCheckRequestDTO:
        return InnCheckRequestDTO(inn=self.inn, ogrn=self.ogrn, kpp=self.kpp, name=self.name)


class CheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    title: str
    status: Literal["passed", "warning", "failed", "skipped"]
    message: str
    # input — matched against what was passed; bank — the stop list and the client card.
    source: Literal["input", "egrul", "fns", "kontur", "bank"]


class FounderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    share_percent: Decimal
    # A legal entity founder; a person — null.
    inn: str | None


class RegistryCompanyRead(BaseModel):
    """ЕГРЮЛ/ЕГРИП."""

    model_config = ConfigDict(from_attributes=True)

    inn: str
    ogrn: str
    kpp: str | None
    legal_form: LegalForm
    name: str
    full_name: str
    registry_status: Literal[
        "active", "liquidating", "liquidated", "bankrupt", "reorganizing", "excluded"
    ]
    registered_at: date
    address: AddressRead
    mass_address: bool
    unreliable: list[Literal["address", "head", "founder"]]
    okved_main: str
    okved_extra: list[str]
    head_name: str
    head_position: str
    head_since: date | None
    founders: list[FounderRead]


class AccountBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision_number: str
    date: date
    reason: str


class TaxRead(BaseModel):
    """The tax service («Прозрачный бизнес»), rubles."""

    model_config = ConfigDict(from_attributes=True)

    tax_regime: str
    avg_headcount: int
    reported_revenue: Decimal | None
    report_year: int | None
    tax_arrears: Decimal
    in_msp_registry: bool
    disqualified_head: bool
    mass_head: bool | None
    account_blocks: list[AccountBlockRead]


class BankruptcyMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    type: str
    case: str


class CounterpartyRead(BaseModel):
    """Kontur: courts, bailiffs, bankruptcy; rubles."""

    model_config = ConfigDict(from_attributes=True)

    reliability: Literal["green", "yellow", "red"]
    notes: list[str]
    arbitration_as_defendant: int
    arbitration_defendant_sum: Decimal
    enforcement_active: int
    enforcement_sum: Decimal
    bankruptcy_messages: list[BankruptcyMessageRead]


class InnCheckRead(BaseModel):
    """The verdict is the worst status of the checks: a failed one — `fail`; a warning or a
    source that did not answer — `warning`; `not_found` — ЕГРЮЛ/ЕГРИП do not know the INN."""

    model_config = ConfigDict(from_attributes=True)

    inn: str
    verdict: Literal["ok", "warning", "fail", "not_found"]
    summary: str
    checked_at: datetime
    checks: list[CheckRead]
    # null — nothing found: an unknown INN or a typo in it.
    company: RegistryCompanyRead | None
    # null — the source did not answer (its checks are `skipped`) or nothing found.
    tax: TaxRead | None
    counterparty: CounterpartyRead | None
    # The company is already a client of the bank: its card.
    organization_id: UUID | None
