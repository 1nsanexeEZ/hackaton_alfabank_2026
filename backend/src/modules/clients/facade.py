"""Clients contract for other modules: who the borrower is and who may act for it.

The only entry point for other modules: the protocol below and the DTO it returns
(defined in `application/dto`, re-exported here)."""

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from src.modules.clients.application.dto.business_plan import (
    BusinessPlanDTO,
    FinancialModelDTO,
    PlanMonthDTO,
    StateGuarantee,
)
from src.modules.clients.application.dto.membership import MemberRole, OrganizationSummaryDTO
from src.modules.clients.application.dto.snapshot import (
    DiscrepancyDTO,
    FinancialReportDTO,
    LegalForm,
    OrganizationSnapshotDTO,
    RegistryStatus,
    ReportSource,
    VerificationStatus,
)

__all__ = [
    "BusinessPlanDTO",
    "ClientsFacade",
    "DiscrepancyDTO",
    "FinancialModelDTO",
    "FinancialReportDTO",
    "LegalForm",
    "MemberRole",
    "OrgPermission",
    "OrganizationSnapshotDTO",
    "OrganizationSummaryDTO",
    "PlanMonthDTO",
    "RegistryStatus",
    "ReportSource",
    "StateGuarantee",
    "VerificationStatus",
]


class OrgPermission(StrEnum):
    """Rights inside a company (not to be confused with token permissions)."""

    VIEW = "view"
    SUBMIT_APPLICATION = "submit_application"
    SIGN = "sign"
    MANAGE_MEMBERS = "manage_members"
    EDIT_FINANCIALS = "edit_financials"


class ClientsFacade(Protocol):
    async def ensure_can(self, account_id: UUID, organization_id: UUID, permission: str) -> None:
        """Raises PermissionDeniedError; a stranger to the company gets NotFoundError."""
        ...

    async def get_member_permissions(
        self, account_id: UUID, organization_id: UUID
    ) -> frozenset[str]: ...

    async def get_member_organization_ids(self, account_id: UUID) -> frozenset[UUID]: ...

    async def get_snapshot(self, organization_id: UUID) -> OrganizationSnapshotDTO: ...

    async def list_my_organizations(self, account_id: UUID) -> list[OrganizationSummaryDTO]: ...

    async def list_members(
        self, organization_id: UUID, permission: str | None = None
    ) -> list[UUID]: ...

    async def get_registry_head(self, organization_id: UUID) -> UUID | None:
        """The member whose name matched the head in the state registry (authority by the
        registry): the person whose own consent the bank needs for their credit history.
        A director goes before an owner. None — no such member or no company."""
        ...

    async def get_business_plan(self, organization_id: UUID) -> BusinessPlanDTO | None:
        """The startup's business plan and financial model from the cabinet; None — not
        filled in yet."""
        ...
