"""Assembly of the use cases and the facade from the infrastructure implementations."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry, get_facade_registry
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.subscriber import HandlerContext
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.notifications.application.interfaces.repositories import FeedStore
from src.modules.notifications.application.use_cases import stream
from src.modules.notifications.application.use_cases.account_feed import (
    CountAccountUnreadUseCase,
    LatestAccountFeedUseCase,
)
from src.modules.notifications.application.use_cases.feed import (
    CountUnreadUseCase,
    ListFeedUseCase,
    MarkAllFeedReadUseCase,
    MarkFeedItemReadUseCase,
)
from src.modules.notifications.application.use_cases.news import (
    MarkNewsReadUseCase,
    PersonalNewsUseCase,
    ViewerNewsUseCase,
)
from src.modules.notifications.application.use_cases.organizations import (
    EnsureOrganizationVisibleUseCase,
    ViewerOrganizationsUseCase,
)
from src.modules.notifications.application.use_cases.project_event import ProjectEventUseCase
from src.modules.notifications.application.use_cases.stream import (
    IssueStreamTicketUseCase,
    RedeemStreamTicketUseCase,
    StreamFeedUseCase,
)
from src.modules.notifications.domain.feed import UNDERWRITER_ROLE, Recipient
from src.modules.notifications.domain.viewers import is_bank_staff, viewer_recipients
from src.modules.notifications.infrastructure.adapters.neighbours import FacadeNeighbours
from src.modules.notifications.infrastructure.adapters.notifications_facade import (
    NotificationsFacadeImpl,
)
from src.modules.notifications.infrastructure.adapters.organization_access import (
    ClientsOrganizationAccess,
)
from src.modules.notifications.infrastructure.adapters.session_facades import SessionFacades
from src.modules.notifications.infrastructure.repositories.feed import SqlAlchemyFeedStore
from src.modules.notifications.infrastructure.repositories.news import SqlAlchemyNewsStore
from src.modules.notifications.infrastructure.repositories.tickets import SqlAlchemyTicketStore

# --- facade and Kafka --------------------------------------------------------------


def notifications_facade(
    session: AsyncSession, facades: FacadeRegistry, clock: Clock
) -> NotificationsFacadeImpl:
    feed = SqlAlchemyFeedStore(session)
    neighbours = FacadeNeighbours(SessionFacades(facades, session))
    return NotificationsFacadeImpl(
        CountAccountUnreadUseCase(feed, neighbours),
        LatestAccountFeedUseCase(feed, neighbours),
        PersonalNewsUseCase(SqlAlchemyNewsStore(session), neighbours, clock),
    )


def project_event_use_case(ctx: HandlerContext) -> ProjectEventUseCase:
    """The live path: the handler's transaction is committed by the core with the inbox."""
    return ProjectEventUseCase(SqlAlchemyFeedStore(ctx.session), FacadeNeighbours(ctx.facade))


# --- HTTP ----------------------------------------------------------------------------


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


def session_facades(request: Request, session: AsyncSession) -> SessionFacades:
    return SessionFacades(get_facade_registry(request), session)


def get_organization_visibility(
    request: Request, session: DbSession
) -> EnsureOrganizationVisibleUseCase:
    return EnsureOrganizationVisibleUseCase(
        ClientsOrganizationAccess(session_facades(request, session))
    )


def get_viewer_organizations(request: Request, session: DbSession) -> ViewerOrganizationsUseCase:
    return ViewerOrganizationsUseCase(ClientsOrganizationAccess(session_facades(request, session)))


def get_list_feed(session: DbSession) -> ListFeedUseCase:
    return ListFeedUseCase(SqlAlchemyFeedStore(session))


def get_count_unread(session: DbSession) -> CountUnreadUseCase:
    return CountUnreadUseCase(SqlAlchemyFeedStore(session))


def get_mark_feed_item_read(session: DbSession, clock: AppClock) -> MarkFeedItemReadUseCase:
    return MarkFeedItemReadUseCase(
        SqlAlchemyFeedStore(session), SqlAlchemyUnitOfWork(session), clock
    )


def get_mark_all_feed_read(session: DbSession, clock: AppClock) -> MarkAllFeedReadUseCase:
    return MarkAllFeedReadUseCase(
        SqlAlchemyFeedStore(session), SqlAlchemyUnitOfWork(session), clock
    )


def get_viewer_news(request: Request, session: DbSession, clock: AppClock) -> ViewerNewsUseCase:
    store = SqlAlchemyNewsStore(session)
    neighbours = FacadeNeighbours(session_facades(request, session))
    return ViewerNewsUseCase(PersonalNewsUseCase(store, neighbours, clock), store)


def get_mark_news_read(session: DbSession, clock: AppClock) -> MarkNewsReadUseCase:
    return MarkNewsReadUseCase(SqlAlchemyNewsStore(session), SqlAlchemyUnitOfWork(session), clock)


def get_issue_stream_ticket(session: DbSession, clock: AppClock) -> IssueStreamTicketUseCase:
    return IssueStreamTicketUseCase(
        SqlAlchemyTicketStore(session), SqlAlchemyUnitOfWork(session), clock
    )


def get_redeem_stream_ticket(session: DbSession, clock: AppClock) -> RedeemStreamTicketUseCase:
    return RedeemStreamTicketUseCase(
        SqlAlchemyTicketStore(session), SqlAlchemyUnitOfWork(session), clock
    )


def get_stream_feed(request: Request, clock: AppClock) -> StreamFeedUseCase:
    """Every poll of the stream opens its own short session of the application."""
    session_factory = request.app.state.session_factory

    @asynccontextmanager
    async def open_store() -> AsyncIterator[FeedStore]:
        async with session_factory() as session:
            yield SqlAlchemyFeedStore(session)

    return StreamFeedUseCase(
        open_store,
        clock,
        poll_seconds=stream.POLL_INTERVAL_SECONDS,
        heartbeat_seconds=stream.HEARTBEAT_SECONDS,
        max_seconds=stream.MAX_STREAM_SECONDS,
    )


OrganizationVisibilityDep = Annotated[
    EnsureOrganizationVisibleUseCase, Depends(get_organization_visibility)
]
ViewerOrganizationsDep = Annotated[ViewerOrganizationsUseCase, Depends(get_viewer_organizations)]
ListFeedDep = Annotated[ListFeedUseCase, Depends(get_list_feed)]
CountUnreadDep = Annotated[CountUnreadUseCase, Depends(get_count_unread)]
MarkFeedItemReadDep = Annotated[MarkFeedItemReadUseCase, Depends(get_mark_feed_item_read)]
MarkAllFeedReadDep = Annotated[MarkAllFeedReadUseCase, Depends(get_mark_all_feed_read)]
ViewerNewsDep = Annotated[ViewerNewsUseCase, Depends(get_viewer_news)]
MarkNewsReadDep = Annotated[MarkNewsReadUseCase, Depends(get_mark_news_read)]
IssueStreamTicketDep = Annotated[IssueStreamTicketUseCase, Depends(get_issue_stream_ticket)]
RedeemStreamTicketDep = Annotated[RedeemStreamTicketUseCase, Depends(get_redeem_stream_ticket)]
StreamFeedDep = Annotated[StreamFeedUseCase, Depends(get_stream_feed)]
