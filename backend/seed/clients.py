"""Seed of clients: demo companies, members, financial reports (seed/demo_data.py).

Idempotent: a company is found by INN, a member by account, a report by
period and source; what is there already stays as is. Accounts come from
identity (its seed runs first); a missing account is skipped with a warning.
Seeds publish no events: this is the initial state, not a change.
"""

import calendar
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from seed.demo_data import (
    ACCOUNTS,
    COMPANIES,
    FINANCIALS_BY_CODE,
    DemoAccount,
    DemoCompany,
    DemoMembership,
    DemoPerson,
)
from src.core.domain import Money
from src.core.exceptions.exceptions import AppError
from src.modules.clients.domain.financial_report import ReportFigures, ReportSource
from src.modules.clients.domain.member import Actor
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.rights import HEAD_ROLES, MemberRole
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
)
from src.modules.clients.infrastructure.repositories import (
    SqlAlchemyFinancialReportRepository,
    SqlAlchemyOrganizationRepository,
)
from src.modules.identity.facade import IdentityFacade

if TYPE_CHECKING:
    from seed.run import SeedContext

logger = logging.getLogger(__name__)

BANK = Actor.bank()
REGION_MOSCOW = "77"
ADDRESSES = {
    "romashka": "г. Москва, ул. Тверская, д. 12, стр. 1",
    "ivanov": "г. Москва, ул. Профсоюзная, д. 45",
    "vector": "г. Москва, Варшавское ш., д. 87",
    "zakat": "г. Москва, ул. Сретенка, д. 9",
    "progress": "г. Москва, Каширское ш., д. 61, корп. 3",
    "sboy": "г. Москва, ул. Нижегородская, д. 32",
}
EMPLOYEES = {"romashka": 24, "ivanov": 2, "vector": 57, "zakat": 9, "progress": 31, "sboy": 18}
# A company's first member must be able to manage members: heads go first.
ROLE_ORDER = {"owner": 0, "director": 0, "accountant": 1, "employee": 2}


def months_ago(today: date, months: int) -> date:
    """The same day `months` calendar months back (clamped to the month end)."""
    index = today.year * 12 + today.month - 1 - months
    year, month = divmod(index, 12)
    day = min(today.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def person(demo: DemoPerson) -> PersonName:
    return PersonName(demo.last_name, demo.first_name, demo.middle_name)


def memberships(company: DemoCompany) -> list[tuple[DemoAccount, DemoMembership]]:
    found = [
        (account, membership)
        for account in ACCOUNTS
        for membership in account.memberships
        if membership.company_code == company.code
    ]
    return sorted(found, key=lambda pair: ROLE_ORDER[pair[1].role])


def verification(company: DemoCompany, now: datetime) -> VerificationResult:
    """A declared head who is not the head by the registry is a mismatch
    (Vector: Petrov in the cabinet, Sidorov in ЕГРЮЛ)."""
    head = person(company.registry_head)
    discrepancies = tuple(
        Discrepancy("head_name", person(account.person).short, head.short)
        for account, membership in memberships(company)
        if MemberRole(membership.role) in HEAD_ROLES and not person(account.person).matches(head)
    )
    if discrepancies:
        return VerificationResult.mismatch(now, discrepancies)
    return VerificationResult.verified(now)


def organization(company: DemoCompany, now: datetime) -> Organization:
    entrepreneur = company.legal_form == "IE"
    return Organization.register(
        id=uuid4(),
        requisites=Requisites.of(company.inn, company.ogrn, company.legal_form, company.kpp),
        name=company.name,
        registered_at=months_ago(now.date(), company.registered_months_ago),
        address=Address(ADDRESSES[company.code], REGION_MOSCOW),
        okved_main=OkvedCode(company.okved_main),
        tax_regime=TaxRegime.USN if entrepreneur else TaxRegime.OSN,
        employees_count=EMPLOYEES[company.code],
        registry_status=RegistryStatus(company.registry_status),
        registry_head=person(company.registry_head),
        verification=verification(company, now),
        now=now,
    )


async def add_members(
    org: Organization, company: DemoCompany, identity: IdentityFacade, now: datetime
) -> bool:
    changed = False
    for account, membership in memberships(company):
        # No personal data in the log: company code and role only.
        ref = await identity.find_by_login(account.email)
        if ref is None:
            logger.warning(
                "Demo account missing, member skipped: %s %s", company.code, membership.role
            )
            continue
        if org.is_member(ref.id):
            continue
        try:
            member = org.add_member(
                BANK, ref.id, MemberRole(membership.role), now, person=person(account.person)
            )
        except AppError as error:
            logger.warning(
                "Demo member skipped: %s %s (%s)", company.code, membership.role, error.message
            )
            continue
        if member.authority.value != membership.authority:
            logger.warning(
                "Demo member authority differs: %s %s is %s",
                company.code,
                membership.role,
                member.authority.value,
            )
        changed = True
    org.pull_events()
    return changed


async def add_reports(
    org: Organization,
    company: DemoCompany,
    reports: SqlAlchemyFinancialReportRepository,
    now: datetime,
) -> None:
    """Annual declared reports for the last year and the one before (if known)."""
    finance = FINANCIALS_BY_CODE[company.code]
    items = [
        (
            FiscalPeriod(now.year - 1),
            ReportFigures(
                revenue=Money(finance.declared_revenue),
                expenses=Money(finance.declared_expenses),
            ),
        )
    ]
    if finance.declared_revenue_previous_year is not None:
        items.append(
            (
                FiscalPeriod(now.year - 2),
                ReportFigures(revenue=Money(finance.declared_revenue_previous_year)),
            )
        )
    for period, figures in items:
        if await reports.find(org.id, period, ReportSource.DECLARED) is not None:
            continue
        report = org.submit_financial_report(
            BANK, report_id=uuid4(), period=period, figures=figures, now=now
        )
        report.pull_events()
        await reports.add(report)


async def seed(context: "SeedContext") -> None:
    now = context.clock.now()
    async with context.session_factory() as session:
        organizations = SqlAlchemyOrganizationRepository(session)
        reports = SqlAlchemyFinancialReportRepository(session)
        identity = (
            context.facades.get(IdentityFacade, session)
            if context.facades.has(IdentityFacade)
            else None
        )
        if identity is None:
            logger.warning("IdentityFacade is not registered: demo members are skipped")
        for company in COMPANIES:
            org = await organizations.get_by_inn(company.inn)
            created = org is None
            if org is None:
                org = organization(company, now)
            changed = identity is not None and await add_members(org, company, identity, now)
            if created:
                await organizations.add(org)
            elif changed:
                await organizations.save(org)
            await add_reports(org, company, reports, now)
        await session.commit()
