from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self, TypeAlias
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.types import SafeString
from src.modules.clients.domain.financial_report import FinancialReport
from src.modules.clients.domain.member import Member
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.rights import MemberRole, OrgPermission, ordered
from src.modules.clients.domain.value_objects import RegistryChanges
from src.modules.identity.facade import AccountRefDTO

LegalForm = Literal["LLC", "IE", "JSC"]
Role = Literal["owner", "director", "accountant", "employee"]
Delegable = Literal["submit_application", "sign"]
Amount: TypeAlias = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
SignedAmount: TypeAlias = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]


def _permissions(org: Organization, account_id: UUID, now: datetime) -> list[str]:
    return [p.value for p in ordered(org.permissions_of(account_id, now))]


def _my_role(org: Organization, account_id: UUID) -> str | None:
    return org.member(account_id).role.value if org.is_member(account_id) else None


class OrganizationSummaryRead(BaseModel):
    id: UUID
    name: str
    inn: str
    legal_form: LegalForm
    registry_status: str
    # None — the caller is not a member (bank staff).
    my_role: Role | None
    my_permissions: list[str]

    @classmethod
    def of(cls, org: Organization, account_id: UUID, now: datetime) -> Self:
        return cls(
            id=org.id,
            name=org.name,
            inn=org.requisites.inn.value,
            legal_form=org.legal_form.value,  # type: ignore[arg-type]
            registry_status=org.registry_status.value,
            my_role=_my_role(org, account_id),  # type: ignore[arg-type]
            my_permissions=_permissions(org, account_id, now),
        )


class AddressRead(BaseModel):
    full: str
    region_code: str


class DiscrepancyRead(BaseModel):
    field: str
    declared: str | None
    registry: str | None


class VerificationRead(BaseModel):
    status: Literal["unverified", "verified", "mismatch"]
    checked_at: datetime | None
    discrepancies: list[DiscrepancyRead]


class OrganizationRead(OrganizationSummaryRead):
    ogrn: str
    kpp: str | None
    registered_at: date
    business_age_months: int
    address: AddressRead
    okved_main: str
    okved_extra: list[str]
    tax_regime: str
    employees_count: int
    # Head by the registry (ЕГРЮЛ/ЕГРИП).
    head_name: str | None
    verification: VerificationRead
    version: int

    @classmethod
    def of(cls, org: Organization, account_id: UUID, now: datetime) -> Self:
        summary = OrganizationSummaryRead.of(org, account_id, now)
        requisites = org.requisites
        verification = org.verification
        return cls(
            **summary.model_dump(),
            ogrn=requisites.ogrn.value,
            kpp=requisites.kpp.value if requisites.kpp else None,
            registered_at=org.registered_at,
            business_age_months=org.business_age_months(now),
            address=AddressRead(full=org.address.full, region_code=org.address.region_code),
            okved_main=org.okved_main.value,
            okved_extra=[code.value for code in org.okved_extra],
            tax_regime=org.tax_regime.value,
            employees_count=org.employees_count,
            head_name=org.registry_head.full if org.registry_head else None,
            verification=VerificationRead(
                status=verification.status.value,  # type: ignore[arg-type]
                checked_at=verification.checked_at,
                discrepancies=[
                    DiscrepancyRead(field=d.field, declared=d.declared, registry=d.registry)
                    for d in verification.discrepancies
                ],
            ),
            version=org.version,
        )


class FieldChangeRead(BaseModel):
    # `name`, `address.full`, `address.region_code`, `kpp`, `okved_main`,
    # `okved_extra` (codes joined with ", "), `registry_status`.
    field: str
    before: str | None
    after: str | None


class VerificationResultRead(BaseModel):
    """Outcome of the check against ЕГРЮЛ/ЕГРИП: what followed the registry
    silently and what is left for a person."""

    organization: OrganizationRead
    updated_fields: list[FieldChangeRead]
    discrepancies: list[DiscrepancyRead]

    @classmethod
    def of(
        cls, org: Organization, changes: RegistryChanges, account_id: UUID, now: datetime
    ) -> Self:
        return cls(
            organization=OrganizationRead.of(org, account_id, now),
            updated_fields=[
                FieldChangeRead(field=c.field, before=c.before, after=c.after)
                for c in changes.updated
            ],
            discrepancies=[
                DiscrepancyRead(field=d.field, declared=d.declared, registry=d.registry)
                for d in changes.discrepancies
            ],
        )


class PowerOfAttorneyRead(BaseModel):
    number: str
    issued_at: date
    valid_until: date
    scope: list[str]
    is_valid: bool


class MemberRead(BaseModel):
    account_id: UUID
    role: Role
    authority: Literal["registry", "power_of_attorney", "unconfirmed"]
    power_of_attorney: PowerOfAttorneyRead | None
    # Effective now: an expired power of attorney gives nothing.
    permissions: list[str]
    added_at: datetime
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    position: str | None = None

    @classmethod
    def of(cls, member: Member, account: AccountRefDTO | None, now: datetime) -> Self:
        poa = member.power_of_attorney
        return cls(
            account_id=member.account_id,
            role=member.role.value,  # type: ignore[arg-type]
            authority=member.authority.value,  # type: ignore[arg-type]
            power_of_attorney=PowerOfAttorneyRead(
                number=poa.number,
                issued_at=poa.issued_at,
                valid_until=poa.valid_until,
                scope=[p.value for p in ordered(poa.scope)],
                is_valid=poa.is_valid(now),
            )
            if poa
            else None,
            permissions=[p.value for p in ordered(member.permissions(now))],
            added_at=member.added_at,
            last_name=account.last_name if account else None,
            first_name=account.first_name if account else None,
            middle_name=account.middle_name if account else None,
            position=account.position if account else None,
        )


class MemberCreate(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="Email or phone of the account")
    role: MemberRole


class MemberUpdate(BaseModel):
    role: MemberRole


class PowerOfAttorneyCreate(BaseModel):
    number: SafeString = Field(min_length=1, max_length=64)
    issued_at: date
    valid_until: date
    scope: list[Delegable] = Field(min_length=1)

    def scope_permissions(self) -> frozenset[OrgPermission]:
        return frozenset(OrgPermission(p) for p in self.scope)


class FinancialReportRead(BaseModel):
    id: UUID
    period_year: int
    period_quarter: int | None
    source: Literal["declared", "fns", "bank_statement"]
    revenue: Decimal
    expenses: Decimal | None
    net_profit: Decimal | None
    total_liabilities: Decimal | None
    monthly_debt_payments: Decimal | None
    submitted_by: UUID | None
    submitted_at: datetime

    @classmethod
    def of(cls, report: FinancialReport) -> Self:
        figures = report.figures

        def amount(name: str) -> Decimal | None:
            value = getattr(figures, name)
            return value.amount if value is not None else None

        return cls(
            id=report.id,
            period_year=report.period.year,
            period_quarter=report.period.quarter,
            source=report.source.value,  # type: ignore[arg-type]
            revenue=figures.revenue.amount,
            expenses=amount("expenses"),
            net_profit=amount("net_profit"),
            total_liabilities=amount("total_liabilities"),
            monthly_debt_payments=amount("monthly_debt_payments"),
            submitted_by=report.submitted_by,
            submitted_at=report.submitted_at,
        )


class FinancialReportCreate(BaseModel):
    """Declared figures in roubles for a year (`period_quarter` empty) or a quarter."""

    period_year: int = Field(ge=2000, le=2100)
    period_quarter: int | None = Field(default=None, ge=1, le=4)
    revenue: Amount
    expenses: Amount | None = None
    net_profit: SignedAmount | None = None
    total_liabilities: Amount | None = None
    monthly_debt_payments: Amount | None = None
