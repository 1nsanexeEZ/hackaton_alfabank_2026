from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.facade import ClientsFacade, OrgPermission
from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.core.facades import get_facade_registry
from src.core.infrastructure.database.session import DbSession
from src.core.uow import SqlAlchemyUnitOfWork
from src.notifications.application.feed import FeedService, is_bank_staff, viewer_recipients
from src.notifications.application.neighbours import Neighbours
from src.notifications.application.news import NewsService
from src.notifications.application.stream import StreamTickets
from src.notifications.domain.feed import UNDERWRITER_ROLE, Recipient
from src.notifications.infrastructure.repositories import (
    SqlAlchemyFeedStore,
    SqlAlchemyNewsStore,
    SqlAlchemyTicketStore,
)


@dataclass(frozen=True, slots=True)
class Viewer:
    account_id: UUID
    # Bank staff read the back office feed and may look at any company.
    bank_staff: bool
    recipients: tuple[Recipient, ...]

    @property
    def roles(self) -> tuple[str, ...]:
        return (UNDERWRITER_ROLE,) if self.bank_staff else ()


async def get_viewer(
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.FEED_READ))],
) -> Viewer:
    bank_staff = is_bank_staff(access.granted_permissions)
    return Viewer(access.user_id, bank_staff, viewer_recipients(access.user_id, bank_staff))


CurrentViewer = Annotated[Viewer, Depends(get_viewer)]


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


AppClock = Annotated[Clock, Depends(get_clock)]


def neighbours_for(request: Request, session: AsyncSession) -> Neighbours:
    registry = get_facade_registry(request)
    return Neighbours(lambda key: registry.get(key, session))


async def ensure_organization_visible(
    request: Request, session: AsyncSession, viewer: Viewer, organization_id: UUID | None
) -> None:
    """A client filters only by its own companies; a stranger's company is 404.
    The clients facade is looked up only when a filter is given."""
    if organization_id is None or viewer.bank_staff:
        return
    clients = get_facade_registry(request).get(ClientsFacade, session)
    try:
        await clients.ensure_can(viewer.account_id, organization_id, OrgPermission.VIEW)
    except PermissionDeniedError:
        raise NotFoundError("Organization not found") from None


def get_feed_service(session: DbSession, clock: AppClock) -> FeedService:
    return FeedService(SqlAlchemyFeedStore(session), SqlAlchemyUnitOfWork(session), clock)


def get_news_service(request: Request, session: DbSession, clock: AppClock) -> NewsService:
    return NewsService(
        SqlAlchemyNewsStore(session),
        neighbours_for(request, session),
        clock,
        SqlAlchemyUnitOfWork(session),
    )


def get_stream_tickets(session: DbSession, clock: AppClock) -> StreamTickets:
    return StreamTickets(SqlAlchemyTicketStore(session), SqlAlchemyUnitOfWork(session), clock)


FeedServiceDep = Annotated[FeedService, Depends(get_feed_service)]
NewsServiceDep = Annotated[NewsService, Depends(get_news_service)]
StreamTicketsDep = Annotated[StreamTickets, Depends(get_stream_tickets)]
