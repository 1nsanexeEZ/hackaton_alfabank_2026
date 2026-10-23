"""Rows <-> domain aggregates of clients."""

from datetime import UTC, date, datetime
from typing import Any

from src.core.domain import Money
from src.modules.clients.domain.enums import (
    Authority,
    MemberRole,
    OrgPermission,
    RegistryStatus,
    ReportSource,
    TaxRegime,
    VerificationStatus,
)
from src.modules.clients.domain.financial_report import FinancialReport, ReportFigures
from src.modules.clients.domain.member import Member
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.rights import PowerOfAttorney
from src.modules.clients.domain.value_objects import (
    Address,
    Discrepancy,
    FiscalPeriod,
    OkvedCode,
    PersonName,
    Requisites,
    VerificationResult,
)
from src.modules.clients.infrastructure.database.models import (
    FinancialReportModel,
    MemberModel,
    OrganizationModel,
)

# An annual report is stored with quarter 0 (see FinancialReportModel).
ANNUAL = 0


def aware(moment: datetime) -> datetime:
    # SQLite gives naive datetimes back; everything is stored in UTC.
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


# --- organization -------------------------------------------------------------


def _person_to_json(person: PersonName | None) -> dict[str, Any] | None:
    if person is None:
        return None
    return {
        "last_name": person.last_name,
        "first_name": person.first_name,
        "middle_name": person.middle_name,
    }


def _person_from_json(data: dict[str, Any] | None) -> PersonName | None:
    if data is None:
        return None
    return PersonName(data["last_name"], data["first_name"], data.get("middle_name"))


def _poa_to_json(poa: PowerOfAttorney | None) -> dict[str, Any] | None:
    if poa is None:
        return None
    return {
        "number": poa.number,
        "issued_at": poa.issued_at.isoformat(),
        "valid_until": poa.valid_until.isoformat(),
        "scope": sorted(p.value for p in poa.scope),
    }


def _poa_from_json(data: dict[str, Any] | None) -> PowerOfAttorney | None:
    if data is None:
        return None
    return PowerOfAttorney(
        number=data["number"],
        issued_at=date.fromisoformat(data["issued_at"]),
        valid_until=date.fromisoformat(data["valid_until"]),
        scope=frozenset(OrgPermission(p) for p in data["scope"]),
    )


def organization_values(org: Organization) -> dict[str, Any]:
    """Columns that may change after registration."""
    verification = org.verification
    kpp = org.requisites.kpp
    return {
        "name": org.name,
        "kpp": kpp.value if kpp else None,
        "address": org.address.full,
        "region_code": org.address.region_code,
        "okved_main": org.okved_main.value,
        "okved_extra": [code.value for code in org.okved_extra],
        "tax_regime": org.tax_regime.value,
        "employees_count": org.employees_count,
        "registry_status": org.registry_status.value,
        "registry_head": _person_to_json(org.registry_head),
        "verification_status": verification.status.value,
        "verification_checked_at": verification.checked_at,
        "verification_discrepancies": [
            {"field": d.field, "declared": d.declared, "registry": d.registry}
            for d in verification.discrepancies
        ],
    }


def member_values(member: Member) -> dict[str, Any]:
    return {
        "role": member.role.value,
        "authority": member.authority.value,
        "power_of_attorney": _poa_to_json(member.power_of_attorney),
        "added_at": member.added_at,
        "added_by": member.added_by,
    }


def _member_to_entity(model: MemberModel) -> Member:
    return Member(
        account_id=model.account_id,
        role=MemberRole(model.role),
        authority=Authority(model.authority),
        added_at=aware(model.added_at),
        added_by=model.added_by,
        power_of_attorney=_poa_from_json(model.power_of_attorney),
    )


def organization_to_entity(model: OrganizationModel, members: list[MemberModel]) -> Organization:
    checked_at = model.verification_checked_at
    return Organization(
        id=model.id,
        requisites=Requisites.of(model.inn, model.ogrn, model.legal_form, model.kpp),
        name=model.name,
        registered_at=model.registered_at,
        address=Address(model.address, model.region_code),
        okved_main=OkvedCode(model.okved_main),
        okved_extra=[OkvedCode(code) for code in model.okved_extra],
        tax_regime=TaxRegime(model.tax_regime),
        employees_count=model.employees_count,
        registry_status=RegistryStatus(model.registry_status),
        registry_head=_person_from_json(model.registry_head),
        verification=VerificationResult(
            status=VerificationStatus(model.verification_status),
            checked_at=aware(checked_at) if checked_at is not None else None,
            discrepancies=tuple(
                Discrepancy(d["field"], d.get("declared"), d.get("registry"))
                for d in model.verification_discrepancies
            ),
        ),
        members=[_member_to_entity(m) for m in sorted(members, key=lambda m: m.added_at)],
        version=model.version,
    )


# --- financial reports --------------------------------------------------------


def _money(value: Any) -> Money | None:
    return Money(value) if value is not None else None


def _amount(value: Money | None) -> Any:
    return value.amount if value is not None else None


def report_to_entity(model: FinancialReportModel) -> FinancialReport:
    return FinancialReport(
        id=model.id,
        organization_id=model.organization_id,
        period=FiscalPeriod(model.period_year, model.period_quarter or None),
        source=ReportSource(model.source),
        figures=ReportFigures(
            revenue=Money(model.revenue),
            expenses=_money(model.expenses),
            net_profit=_money(model.net_profit),
            total_liabilities=_money(model.total_liabilities),
            monthly_debt_payments=_money(model.monthly_debt_payments),
        ),
        submitted_by=model.submitted_by,
        submitted_at=aware(model.submitted_at),
    )


def figures_values(report: FinancialReport) -> dict[str, Any]:
    figures = report.figures
    return {
        "revenue": figures.revenue.amount,
        "expenses": _amount(figures.expenses),
        "net_profit": _amount(figures.net_profit),
        "total_liabilities": _amount(figures.total_liabilities),
        "monthly_debt_payments": _amount(figures.monthly_debt_payments),
        "submitted_by": report.submitted_by,
        "submitted_at": report.submitted_at,
    }
