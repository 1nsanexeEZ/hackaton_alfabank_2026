"""Use cases of the companies API.

Row access comes from the AccessContext (the `org_member` policy hides
other companies: they are simply not found), rights inside the company — from
the aggregate. Every change and its events are committed together.
"""

from datetime import datetime
from uuid import UUID, uuid4

from src.clients.application.events import stage
from src.clients.application.ports import (
    EventOutbox,
    FinancialReportRepository,
    OrganizationRepository,
)
from src.clients.domain.financial_report import FinancialReport, ReportFigures, ReportSource
from src.clients.domain.member import Actor, Member
from src.clients.domain.organization import Organization, organization_not_found
from src.clients.domain.rights import MemberRole, OrgPermission, PowerOfAttorney
from src.clients.domain.value_objects import FiscalPeriod, PersonName
from src.core.access.access_context import AccessContext
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ValidationError
from src.core.uow import UnitOfWork
from src.identity.facade import AccountRefDTO, IdentityFacade


def actor_of(access: AccessContext) -> Actor:
    """An admin acts for the bank; everybody else — as a member of the company."""
    if Permissions.ADMIN.value in access.granted_permissions:
        return Actor.bank(access.user_id)
    return Actor.member(access.user_id)


def person_of(account: AccountRefDTO) -> PersonName | None:
    try:
        return PersonName(account.last_name, account.first_name, account.middle_name)
    except ValidationError:
        return None


class OrganizationService:
    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        reports: FinancialReportRepository,
        outbox: EventOutbox,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._reports = reports
        self._outbox = outbox
        self._clock = clock

    def now(self) -> datetime:
        return self._clock.now()

    # --- reading ------------------------------------------------------------

    async def list_visible(self, access: AccessContext) -> list[Organization]:
        """A client sees the companies he is a member of, the bank — all of them."""
        return await self._organizations.list_visible(access)

    async def get(self, access: AccessContext, organization_id: UUID) -> Organization:
        org = await self._organizations.get(organization_id, access)
        if org is None:
            raise organization_not_found()
        return org

    async def list_members(
        self, access: AccessContext, organization_id: UUID, identity: IdentityFacade
    ) -> list[tuple[Member, AccountRefDTO | None]]:
        org = await self.get(access, organization_id)
        return [(m, await identity.get_account(m.account_id)) for m in org.members]

    async def list_reports(
        self, access: AccessContext, organization_id: UUID
    ) -> list[FinancialReport]:
        org = await self.get(access, organization_id)
        return await self._reports.list_for(org.id)

    # --- members ------------------------------------------------------------

    async def add_member(
        self,
        access: AccessContext,
        organization_id: UUID,
        login: str,
        role: MemberRole,
        identity: IdentityFacade,
    ) -> tuple[Member, AccountRefDTO]:
        """The account must exist already: there is no registration."""
        async with self._uow:
            org = await self.get(access, organization_id)
            # Rights first: a member without manage_members learns nothing about logins.
            actor = actor_of(access)
            if not actor.is_bank:
                org.ensure_can(access.user_id, OrgPermission.MANAGE_MEMBERS, self.now())
            account = await identity.find_by_login(login.strip())
            if account is None:
                raise ValidationError(
                    "No account with this login",
                    details={"field": "login", "code": "account_not_found"},
                )
            member = org.add_member(actor, account.id, role, self.now(), person=person_of(account))
            await self._commit(org)
        return member, account

    async def change_role(
        self, access: AccessContext, organization_id: UUID, account_id: UUID, role: MemberRole
    ) -> Member:
        async with self._uow:
            org = await self.get(access, organization_id)
            member = org.change_role(actor_of(access), account_id, role, self.now())
            await self._commit(org)
        return member

    async def remove_member(
        self, access: AccessContext, organization_id: UUID, account_id: UUID
    ) -> None:
        async with self._uow:
            org = await self.get(access, organization_id)
            org.remove_member(actor_of(access), account_id, self.now())
            await self._commit(org)

    async def grant_power_of_attorney(
        self,
        access: AccessContext,
        organization_id: UUID,
        account_id: UUID,
        power_of_attorney: PowerOfAttorney,
    ) -> Member:
        async with self._uow:
            org = await self.get(access, organization_id)
            member = org.grant_power_of_attorney(
                actor_of(access), account_id, power_of_attorney, self.now()
            )
            await self._commit(org)
        return member

    # --- financial reports --------------------------------------------------

    async def submit_report(
        self,
        access: AccessContext,
        organization_id: UUID,
        period: FiscalPeriod,
        figures: ReportFigures,
    ) -> tuple[FinancialReport, bool]:
        """Declared report; returns it and whether it is new (False — revised)."""
        async with self._uow:
            org = await self.get(access, organization_id)
            existing = await self._reports.find(org.id, period, ReportSource.DECLARED)
            report = org.submit_financial_report(
                actor_of(access),
                report_id=uuid4(),
                period=period,
                figures=figures,
                now=self.now(),
                existing=existing,
            )
            if existing is None:
                await self._reports.add(report)
            else:
                await self._reports.save(report)
            await stage(self._outbox, report.pull_events(), correlation_id=uuid4())
            await self._uow.commit()
        return report, existing is None

    async def _commit(self, org: Organization) -> None:
        await self._organizations.save(org)
        await stage(self._outbox, org.pull_events(), correlation_id=uuid4())
        await self._uow.commit()
