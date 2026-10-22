"""Repositories of clients: map the domain aggregates to the tables and back.

Methods taking an AccessContext are row-level filtered by the caller's
policies (`org_member`: only companies the user is a member of); the rest are
internal lookups for facades and seeds.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.core.domain import Money
from src.core.exceptions.exceptions import ConflictError
from src.core.infrastructure.database.mixins import utcnow
from src.modules.clients.domain.financial_report import FinancialReport, ReportFigures, ReportSource
from src.modules.clients.domain.member import Member
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.rights import Authority, MemberRole, OrgPermission, PowerOfAttorney
from src.modules.clients.domain.value_objects import (
    Address,
    Discrepancy,
    FiscalPeriod,
    OkvedCode,
    PersonName,
    RegistryStatus,
    Requisites,
    TaxRegime,
    VerificationResult,
    VerificationStatus,
)
from src.modules.clients.infrastructure.models import (
    FinancialReportModel,
    MemberModel,
    OrganizationModel,
)

# An annual report is stored with quarter 0 (see FinancialReportModel).
ANNUAL = 0


def _aware(moment: datetime) -> datetime:
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


def _organization_values(org: Organization) -> dict[str, Any]:
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


def _member_values(member: Member) -> dict[str, Any]:
    return {
        "role": member.role.value,
        "authority": member.authority.value,
        "power_of_attorney": _poa_to_json(member.power_of_attorney),
        "added_at": member.added_at,
        "added_by": member.added_by,
    }


def _member_from_model(model: MemberModel) -> Member:
    return Member(
        account_id=model.account_id,
        role=MemberRole(model.role),
        authority=Authority(model.authority),
        added_at=_aware(model.added_at),
        added_by=model.added_by,
        power_of_attorney=_poa_from_json(model.power_of_attorney),
    )


def _organization_from_model(model: OrganizationModel, members: list[MemberModel]) -> Organization:
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
            checked_at=_aware(checked_at) if checked_at is not None else None,
            discrepancies=tuple(
                Discrepancy(d["field"], d.get("declared"), d.get("registry"))
                for d in model.verification_discrepancies
            ),
        ),
        members=[_member_from_model(m) for m in sorted(members, key=lambda m: m.added_at)],
        version=model.version,
    )


class SqlAlchemyOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: UUID, access: AccessContext | None = None
    ) -> Organization | None:
        stmt = select(OrganizationModel).where(OrganizationModel.id == organization_id)
        if access is not None:
            stmt = apply_access_context(stmt, OrganizationModel, access)
        models = await self._load(stmt)
        return models[0] if models else None

    async def list_visible(self, access: AccessContext) -> list[Organization]:
        stmt = apply_access_context(select(OrganizationModel), OrganizationModel, access)
        return await self._load(stmt.order_by(OrganizationModel.name, OrganizationModel.id))

    async def list_for_member(self, account_id: UUID) -> list[Organization]:
        ids = select(MemberModel.organization_id).where(MemberModel.account_id == account_id)
        stmt = select(OrganizationModel).where(OrganizationModel.id.in_(ids))
        return await self._load(stmt.order_by(OrganizationModel.name, OrganizationModel.id))

    async def get_by_inn(self, inn: str) -> Organization | None:
        models = await self._load(select(OrganizationModel).where(OrganizationModel.inn == inn))
        return models[0] if models else None

    async def member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        stmt = select(MemberModel.organization_id).where(MemberModel.account_id == account_id)
        return frozenset((await self._session.scalars(stmt)).all())

    async def add(self, org: Organization) -> None:
        requisites = org.requisites
        self._session.add(
            OrganizationModel(
                id=org.id,
                inn=requisites.inn.value,
                ogrn=requisites.ogrn.value,
                legal_form=requisites.legal_form.value,
                registered_at=org.registered_at,
                version=org.version,
                **_organization_values(org),
            )
        )
        # Members reference the company: its row goes first.
        await self._session.flush()
        for member in org.members:
            self._session.add(
                MemberModel(
                    organization_id=org.id, account_id=member.account_id, **_member_values(member)
                )
            )
        await self._session.flush()

    async def save(self, org: Organization) -> None:
        """Optimistic locking: a concurrent change of the same company (e.g. two
        managers removing each other) gets a ConflictError instead of breaking
        the invariants checked on a stale copy."""
        result = await self._session.execute(
            update(OrganizationModel)
            .where(OrganizationModel.id == org.id, OrganizationModel.version == org.version)
            .values(version=org.version + 1, updated_at=utcnow(), **_organization_values(org))
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ConflictError(
                "Organization was changed by someone else, retry",
                details={"code": "version_conflict"},
            )
        org.version += 1

        stored = {
            m.account_id: m
            for m in (
                await self._session.scalars(
                    select(MemberModel).where(MemberModel.organization_id == org.id)
                )
            ).all()
        }
        current = {m.account_id: m for m in org.members}
        removed = set(stored) - set(current)
        if removed:
            await self._session.execute(
                delete(MemberModel)
                .where(MemberModel.organization_id == org.id, MemberModel.account_id.in_(removed))
                .execution_options(synchronize_session="fetch")
            )
        for account_id, member in current.items():
            model = stored.get(account_id)
            if model is None:
                self._session.add(
                    MemberModel(
                        organization_id=org.id, account_id=account_id, **_member_values(member)
                    )
                )
            else:
                for name, value in _member_values(member).items():
                    setattr(model, name, value)
        await self._session.flush()

    async def _load(self, stmt: Any) -> list[Organization]:
        # populate_existing: a company saved earlier in this session is read fresh.
        fresh = {"populate_existing": True}
        models: Sequence[OrganizationModel] = (
            await self._session.scalars(stmt.execution_options(**fresh))
        ).all()
        if not models:
            return []
        rows = await self._session.scalars(
            select(MemberModel)
            .where(MemberModel.organization_id.in_([m.id for m in models]))
            .execution_options(**fresh)
        )
        members: dict[UUID, list[MemberModel]] = defaultdict(list)
        for row in rows.all():
            members[row.organization_id].append(row)
        return [_organization_from_model(m, members[m.id]) for m in models]


# --- financial reports --------------------------------------------------------


def _money(value: Any) -> Money | None:
    return Money(value) if value is not None else None


def _amount(value: Money | None) -> Any:
    return value.amount if value is not None else None


def _report_from_model(model: FinancialReportModel) -> FinancialReport:
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
        submitted_at=_aware(model.submitted_at),
    )


def _figures_values(report: FinancialReport) -> dict[str, Any]:
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


class SqlAlchemyFinancialReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for(self, organization_id: UUID) -> list[FinancialReport]:
        """Newest year first; within a year — the annual report, then quarters 4..1."""
        stmt = select(FinancialReportModel).where(
            FinancialReportModel.organization_id == organization_id
        )
        models = (await self._session.scalars(stmt)).all()
        ordered = sorted(
            models,
            key=lambda m: (-m.period_year, m.period_quarter != ANNUAL, -m.period_quarter, m.source),
        )
        return [_report_from_model(m) for m in ordered]

    async def find(
        self, organization_id: UUID, period: FiscalPeriod, source: ReportSource
    ) -> FinancialReport | None:
        model = await self._find_model(organization_id, period, source)
        return _report_from_model(model) if model is not None else None

    async def add(self, report: FinancialReport) -> None:
        self._session.add(
            FinancialReportModel(
                id=report.id,
                organization_id=report.organization_id,
                period_year=report.period.year,
                period_quarter=report.period.quarter or ANNUAL,
                source=report.source.value,
                **_figures_values(report),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            # Someone stored a report for the same period meanwhile.
            raise ConflictError(
                "A report for this period is being submitted already, retry",
                details={"code": "report_exists"},
            ) from None

    async def save(self, report: FinancialReport) -> None:
        model = await self._session.get(FinancialReportModel, report.id)
        if model is None:
            raise LookupError(f"Financial report {report.id} is not stored")
        for name, value in _figures_values(report).items():
            setattr(model, name, value)
        await self._session.flush()

    async def _find_model(
        self, organization_id: UUID, period: FiscalPeriod, source: ReportSource
    ) -> FinancialReportModel | None:
        stmt = select(FinancialReportModel).where(
            FinancialReportModel.organization_id == organization_id,
            FinancialReportModel.period_year == period.year,
            FinancialReportModel.period_quarter == (period.quarter or ANNUAL),
            FinancialReportModel.source == source.value,
        )
        return (await self._session.scalars(stmt)).one_or_none()
