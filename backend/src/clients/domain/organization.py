"""Organization — the aggregate root of clients: who the borrower is and who
may act for it.

Invariants:
- requisites never change after registration;
- an account is a member at most once;
- a company with members always has one who can manage members: the last
  one cannot be removed or demoted;
- only a member with `manage_members` (or the bank) changes the members;
- an entrepreneur (IE) has exactly one owner — the entrepreneur himself
  (his name matches the registry), and no director;
- `sign` needs confirmed authority: by the registry or by a power of
  attorney valid at `now`, which only a head confirmed by the registry issues.

The registry status does not block anything here: the stop factor belongs to
decision.
"""

from collections.abc import Iterable
from datetime import date, datetime
from typing import Self
from uuid import UUID

from src.clients.domain.events import (
    MemberAdded,
    MemberRemoved,
    MemberRoleChanged,
    OrganizationEvent,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.clients.domain.financial_report import FinancialReport, ReportFigures, ReportSource
from src.clients.domain.member import Actor, Member
from src.clients.domain.rights import (
    HEAD_ROLES,
    Authority,
    MemberRole,
    OrgPermission,
    PowerOfAttorney,
)
from src.clients.domain.value_objects import (
    ENTREPRENEUR_ONLY_REGIMES,
    Address,
    FiscalPeriod,
    LegalForm,
    OkvedCode,
    PersonName,
    RegistryStatus,
    Requisites,
    TaxRegime,
    VerificationResult,
    VerificationStatus,
)
from src.core.exceptions.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

MAX_NAME_LENGTH = 255
MAX_EMPLOYEES = 1_000_000


def months_between(start: date, end: date) -> int:
    """Full calendar months from `start` to `end`."""
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def organization_not_found() -> NotFoundError:
    # A stranger must not learn that the company exists.
    return NotFoundError("Organization not found")


class Organization:
    def __init__(
        self,
        *,
        id: UUID,
        requisites: Requisites,
        name: str,
        registered_at: date,
        address: Address,
        okved_main: OkvedCode,
        tax_regime: TaxRegime,
        employees_count: int,
        registry_status: RegistryStatus,
        okved_extra: Iterable[OkvedCode] = (),
        registry_head: PersonName | None = None,
        verification: VerificationResult | None = None,
        members: Iterable[Member] = (),
        version: int = 1,
    ) -> None:
        if not name.strip() or len(name) > MAX_NAME_LENGTH:
            raise ValidationError(
                "Company name is empty or too long", details={"field": "name", "code": "invalid"}
            )
        if not 0 <= employees_count <= MAX_EMPLOYEES:
            raise ValidationError(
                "Employees count is out of range",
                details={"field": "employees_count", "code": "out_of_range"},
            )
        if tax_regime in ENTREPRENEUR_ONLY_REGIMES and not requisites.legal_form.is_entrepreneur:
            raise ValidationError(
                "This tax regime is for entrepreneurs only",
                details={"field": "tax_regime", "code": "not_allowed"},
            )
        self.id = id
        self._requisites = requisites
        self.name = name
        self.registered_at = registered_at
        self.address = address
        self.okved_main = okved_main
        self.okved_extra: tuple[OkvedCode, ...] = tuple(okved_extra)
        self.tax_regime = tax_regime
        self.employees_count = employees_count
        self.registry_status = registry_status
        # Head by the registry: director of an LLC/JSC, the entrepreneur of an IE.
        self.registry_head = registry_head
        self.verification = verification or VerificationResult()
        self._members: dict[UUID, Member] = {m.account_id: m for m in members}
        self.version = version
        self._events: list[OrganizationEvent] = []

    @classmethod
    def register(
        cls,
        *,
        id: UUID,
        requisites: Requisites,
        name: str,
        registered_at: date,
        address: Address,
        okved_main: OkvedCode,
        tax_regime: TaxRegime,
        employees_count: int,
        registry_status: RegistryStatus,
        now: datetime,
        okved_extra: Iterable[OkvedCode] = (),
        registry_head: PersonName | None = None,
        verification: VerificationResult | None = None,
    ) -> Self:
        """A company known to the bank; members are added afterwards."""
        if registered_at > now.date():
            raise ValidationError(
                "Registration date is in the future",
                details={"field": "registered_at", "code": "in_future"},
            )
        return cls(
            id=id,
            requisites=requisites,
            name=name,
            registered_at=registered_at,
            address=address,
            okved_main=okved_main,
            okved_extra=okved_extra,
            tax_regime=tax_regime,
            employees_count=employees_count,
            registry_status=registry_status,
            registry_head=registry_head,
            verification=verification,
        )

    # --- reading ------------------------------------------------------------

    @property
    def requisites(self) -> Requisites:
        return self._requisites

    @property
    def legal_form(self) -> LegalForm:
        return self._requisites.legal_form

    @property
    def members(self) -> tuple[Member, ...]:
        return tuple(self._members.values())

    def is_member(self, account_id: UUID) -> bool:
        return account_id in self._members

    def member(self, account_id: UUID) -> Member:
        try:
            return self._members[account_id]
        except KeyError:
            raise NotFoundError("Member not found") from None

    def permissions_of(self, account_id: UUID, now: datetime) -> frozenset[OrgPermission]:
        member = self._members.get(account_id)
        return member.permissions(now) if member else frozenset()

    def can(self, account_id: UUID, permission: OrgPermission, now: datetime) -> bool:
        return permission in self.permissions_of(account_id, now)

    def ensure_can(self, account_id: UUID, permission: OrgPermission, now: datetime) -> None:
        """A stranger gets NotFoundError (the company is hidden), a member
        without the right — PermissionDeniedError."""
        if account_id not in self._members:
            raise organization_not_found()
        if not self.can(account_id, permission, now):
            raise PermissionDeniedError(
                "Not enough rights in the organization",
                details={"code": "org_permission_required", "permission": permission.value},
            )

    def members_with(self, permission: OrgPermission | None, now: datetime) -> list[UUID]:
        return [
            m.account_id
            for m in self._members.values()
            if permission is None or m.can(permission, now)
        ]

    def business_age_months(self, now: datetime) -> int:
        return months_between(self.registered_at, now.date())

    def pull_events(self) -> list[OrganizationEvent]:
        events, self._events = self._events, []
        return events

    # --- members ------------------------------------------------------------

    def add_member(
        self,
        actor: Actor,
        account_id: UUID,
        role: MemberRole,
        now: datetime,
        *,
        person: PersonName | None = None,
        power_of_attorney: PowerOfAttorney | None = None,
    ) -> Member:
        """`person` — the account's name: a head whose name matches the
        registry gets authority by the registry, otherwise it stays
        unconfirmed (or rests on the power of attorney)."""
        self._ensure_manages_members(actor, now)
        if account_id in self._members:
            raise ConflictError(
                "Account is already a member of the organization",
                details={"code": "already_member"},
            )
        self._ensure_role_allowed(role)
        authority = self._authority_for(role, person)
        if self.legal_form.is_entrepreneur and role is MemberRole.OWNER:
            if any(m.role is MemberRole.OWNER for m in self._members.values()):
                raise ConflictError(
                    "An entrepreneur has exactly one owner", details={"code": "owner_exists"}
                )
            if authority is not Authority.REGISTRY:
                raise ValidationError(
                    "The owner of an entrepreneur is the entrepreneur himself",
                    details={"field": "role", "code": "owner_must_be_entrepreneur"},
                )
        if power_of_attorney is not None:
            self._ensure_issues_power_of_attorney(actor, account_id, power_of_attorney, now)
            if authority is Authority.UNCONFIRMED:
                authority = Authority.POWER_OF_ATTORNEY
        member = Member(
            account_id=account_id,
            role=role,
            authority=authority,
            added_at=now,
            added_by=actor.account_id,
            power_of_attorney=power_of_attorney,
        )
        if not self._managers(now) and not member.can(OrgPermission.MANAGE_MEMBERS, now):
            raise ValidationError(
                "The first member must be able to manage members",
                details={"field": "role", "code": "manager_required"},
            )
        self._members[account_id] = member
        self._events.append(
            MemberAdded(
                occurred_at=now, organization_id=self.id, account_id=account_id, role=role.value
            )
        )
        return member

    def change_role(
        self, actor: Actor, account_id: UUID, role: MemberRole, now: datetime
    ) -> Member:
        """Authority stays as it was: a new head is not confirmed by a role change."""
        self._ensure_manages_members(actor, now)
        member = self.member(account_id)
        if member.role is role:
            return member
        self._ensure_role_allowed(role)
        if self.legal_form.is_entrepreneur and MemberRole.OWNER in (member.role, role):
            raise ConflictError(
                "The owner of an entrepreneur cannot change",
                details={"code": "entrepreneur_owner_fixed"},
            )
        previous = member.role
        member.role = role
        if not self._managers(now):
            member.role = previous
            raise self._last_manager()
        self._events.append(
            MemberRoleChanged(
                occurred_at=now,
                organization_id=self.id,
                account_id=account_id,
                role=role.value,
                previous_role=previous.value,
            )
        )
        return member

    def remove_member(self, actor: Actor, account_id: UUID, now: datetime) -> None:
        self._ensure_manages_members(actor, now)
        member = self.member(account_id)
        if self._managers(now) == [member.account_id]:
            raise self._last_manager()
        del self._members[account_id]
        self._events.append(
            MemberRemoved(occurred_at=now, organization_id=self.id, account_id=account_id)
        )

    def grant_power_of_attorney(
        self,
        actor: Actor,
        account_id: UUID,
        power_of_attorney: PowerOfAttorney,
        now: datetime,
    ) -> Member:
        """Replaces the previous power of attorney of the member."""
        self._ensure_issues_power_of_attorney(actor, account_id, power_of_attorney, now)
        member = self.member(account_id)
        member.power_of_attorney = power_of_attorney
        if member.authority is Authority.UNCONFIRMED:
            member.authority = Authority.POWER_OF_ATTORNEY
        return member

    # --- registry and financials ----------------------------------------------

    def record_verification(self, result: VerificationResult, now: datetime) -> None:
        self.verification = result
        if result.status is VerificationStatus.VERIFIED:
            self._events.append(OrganizationVerified(occurred_at=now, organization_id=self.id))
        elif result.status is VerificationStatus.MISMATCH:
            self._events.append(
                OrganizationVerificationMismatch(
                    occurred_at=now, organization_id=self.id, discrepancies=result.discrepancies
                )
            )

    def submit_financial_report(
        self,
        actor: Actor,
        *,
        report_id: UUID,
        period: FiscalPeriod,
        figures: ReportFigures,
        now: datetime,
        source: ReportSource = ReportSource.DECLARED,
        existing: FinancialReport | None = None,
    ) -> FinancialReport:
        """A member with `edit_financials` declares figures; other sources
        come from the bank. `existing` — the report already stored for this
        period and source: it is revised, not duplicated."""
        if not actor.is_bank:
            assert actor.account_id is not None
            self.ensure_can(actor.account_id, OrgPermission.EDIT_FINANCIALS, now)
            if source is not ReportSource.DECLARED:
                raise PermissionDeniedError(
                    "Only the bank records reports from other sources",
                    details={"code": "source_not_allowed", "source": source.value},
                )
        if existing is not None:
            if (
                existing.organization_id != self.id
                or existing.period != period
                or existing.source is not source
            ):
                raise ValueError("Existing report is for another company, period or source")
            existing.revise(figures, actor.account_id, now)
            return existing
        return FinancialReport.submit(
            id=report_id,
            organization_id=self.id,
            period=period,
            source=source,
            figures=figures,
            submitted_by=actor.account_id,
            now=now,
        )

    # --- internals ----------------------------------------------------------

    def _managers(self, now: datetime) -> list[UUID]:
        return self.members_with(OrgPermission.MANAGE_MEMBERS, now)

    def _ensure_manages_members(self, actor: Actor, now: datetime) -> None:
        if actor.is_bank:
            return
        assert actor.account_id is not None
        self.ensure_can(actor.account_id, OrgPermission.MANAGE_MEMBERS, now)

    def _ensure_issues_power_of_attorney(
        self,
        actor: Actor,
        account_id: UUID,
        power_of_attorney: PowerOfAttorney,
        now: datetime,
    ) -> None:
        """Only a head confirmed by the registry signs a power of attorney:
        an unconfirmed director cannot empower himself or anyone else."""
        if power_of_attorney.is_expired(now):
            raise ValidationError(
                "Power of attorney has expired",
                details={"field": "valid_until", "code": "expired"},
            )
        if actor.is_bank:
            return
        assert actor.account_id is not None
        if actor.account_id not in self._members:
            raise organization_not_found()
        issuer = self._members[actor.account_id]
        if issuer.role not in HEAD_ROLES or issuer.authority is not Authority.REGISTRY:
            raise PermissionDeniedError(
                "Only a head confirmed by the registry issues a power of attorney",
                details={"code": "cannot_issue_power_of_attorney"},
            )
        if actor.account_id == account_id:
            raise ValidationError(
                "A power of attorney cannot be issued to yourself",
                details={"field": "account_id", "code": "self_power_of_attorney"},
            )

    def _ensure_role_allowed(self, role: MemberRole) -> None:
        if self.legal_form.is_entrepreneur and role is MemberRole.DIRECTOR:
            raise ValidationError(
                "An entrepreneur has no director", details={"field": "role", "code": "not_allowed"}
            )

    def _authority_for(self, role: MemberRole, person: PersonName | None) -> Authority:
        if (
            role in HEAD_ROLES
            and person is not None
            and self.registry_head is not None
            and person.matches(self.registry_head)
        ):
            return Authority.REGISTRY
        return Authority.UNCONFIRMED

    @staticmethod
    def _last_manager() -> ConflictError:
        return ConflictError(
            "The company must keep a member who manages members",
            details={"code": "last_manager"},
        )
