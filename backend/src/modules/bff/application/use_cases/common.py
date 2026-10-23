"""What the client screens share: access to the company and its segment.

Lists and counters come from the projector; the card and the status of one
application always come from applications, the source of truth, so the client
sees the result of an action right away. Access to the company is checked
before anything is read: the projector has no checks of its own."""

from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.modules.bff.application.interfaces.neighbours import Neighbours
from src.modules.bff.domain.enums import Segment
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO, OrgPermission
from src.modules.products.facade import STARTUP_AGE_MONTHS


async def ensure_visible(
    neighbours: Neighbours, access: AccessContext, organization_id: UUID
) -> None:
    """A stranger's company is 404: its existence is not disclosed."""
    member_of = access.organization_ids
    if member_of is not None and organization_id not in member_of:
        raise NotFoundError("Organization not found")
    try:
        await neighbours(ClientsFacade).ensure_can(
            access.user_id, organization_id, OrgPermission.VIEW
        )
    except PermissionDeniedError:
        raise NotFoundError("Organization not found") from None


def segment_of(snapshot: OrganizationSnapshotDTO) -> Segment:
    """A startup has no turnover yet: younger than the youngest product allows or without an
    annual report. It gets the founder's prescreen and the startup product."""
    annual = [r for r in snapshot.financial_reports if r.period_quarter is None]
    if snapshot.business_age_months < STARTUP_AGE_MONTHS or not annual:
        return "startup"
    return "established"
