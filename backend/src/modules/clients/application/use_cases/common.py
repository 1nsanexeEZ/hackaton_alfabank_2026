"""What the use cases of clients share: who acts, which company the caller
may see and change, how a change goes to the outbox.

Row access comes from the AccessContext (the `org_member` policy hides
other companies: they are simply not found), rights inside the company — from
the aggregate. Every change and its events are committed together.
"""

from uuid import UUID, uuid4

from src.core.access.access_context import AccessContext
from src.core.access.permissions import Permissions
from src.core.exceptions.exceptions import PermissionDeniedError, ValidationError
from src.modules.clients.application.interfaces.outbox import EventOutbox
from src.modules.clients.application.interfaces.repositories import OrganizationRepository
from src.modules.clients.application.mappers.events import stage
from src.modules.clients.domain.member import Actor
from src.modules.clients.domain.organization import Organization, organization_not_found
from src.modules.clients.domain.value_objects import PersonName
from src.modules.identity.facade import AccountRefDTO


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


async def get_organization(
    organizations: OrganizationRepository,
    organization_id: UUID,
    access: AccessContext | None = None,
) -> Organization:
    """With `access` — NotFoundError also for a company hidden by the caller's policies."""
    org = await organizations.get(organization_id, access)
    if org is None:
        raise organization_not_found()
    return org


async def get_to_change(
    organizations: OrganizationRepository, access: AccessContext, organization_id: UUID
) -> Organization:
    """Members and reports are changed by a member or the admin. Bank staff
    see every company (no `org_member` policy), so for them it is 403, not
    404: the company is not hidden. They only run the registry check."""
    org = await get_organization(organizations, organization_id, access)
    if not actor_of(access).is_bank and not org.is_member(access.user_id):
        raise PermissionDeniedError(
            "Only a member of the company changes it", details={"code": "not_a_member"}
        )
    return org


async def save_with_events(
    organizations: OrganizationRepository, outbox: EventOutbox, org: Organization
) -> None:
    """The company and its events in the current transaction; the caller commits."""
    await organizations.save(org)
    await stage(outbox, org.pull_events(), correlation_id=uuid4())
