"""What the use cases of applications share.

Access is checked twice, on purpose:
- rows: the repository applies the caller's policies (`org_member` — only
  applications of the caller's companies; a stranger gets 404);
- rights inside the company: `clients.ensure_can(...)` — who may submit,
  who may sign (an accountant without a power of attorney may not).
Bank staff read without a company check; writing is not given to them.
"""

from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.uow import UnitOfWork
from src.modules.applications.application.dto.views import ApplicationViewDTO
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.mappers.dto import application_view
from src.modules.applications.application.mappers.messages import to_contract
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.value_objects import Violation
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO, OrgPermission


async def get_writable(
    repository: ApplicationRepository,
    clients: ClientsFacade,
    access: AccessContext,
    application_id: UUID,
    permission: OrgPermission,
) -> CreditApplication:
    application = await repository.get(application_id, access)
    await clients.ensure_can(access.user_id, application.organization_id, permission)
    return application


async def publish(
    application: CreditApplication, outbox: MessageOutbox, causation_id: UUID | None = None
) -> None:
    """The events the aggregate collected, into the outbox of the same transaction."""
    for event in application.pull_events():
        await outbox.add(
            to_contract(event),
            key=application.id,
            correlation_id=application.id,
            causation_id=causation_id,
        )


async def save(
    uow: UnitOfWork,
    repository: ApplicationRepository,
    outbox: MessageOutbox,
    application: CreditApplication,
) -> None:
    """The aggregate, its history and the outgoing events — one transaction."""
    async with uow:
        await repository.save(application)
        await publish(application, outbox)
        await uow.commit()


async def view(
    clients: ClientsFacade, access: AccessContext, application: CreditApplication
) -> ApplicationViewDTO:
    organization: OrganizationSnapshotDTO | None = None
    permissions: frozenset[str] = frozenset()
    if access.organization_ids is not None:  # a client, not bank staff
        permissions = await clients.get_member_permissions(
            access.user_id, application.organization_id
        )
    if application.org_snapshot is None:
        organization = await clients.get_snapshot(application.organization_id)
    return application_view(application, organization, permissions)


async def violations(
    repository: ApplicationRepository, clients: ClientsFacade, application: CreditApplication
) -> list[Violation]:
    """What is still missing before the application can be submitted."""
    if application.org_snapshot is not None:
        legal_form = application.org_snapshot.legal_form
    else:
        legal_form = (await clients.get_snapshot(application.organization_id)).legal_form
    other = await repository.find_active(
        application.organization_id, application.product_code, exclude_id=application.id
    )
    return application.check_ready(legal_form, has_other_active=other is not None)
