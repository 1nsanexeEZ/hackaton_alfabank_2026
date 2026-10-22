from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from src.core.infrastructure.database.session import DbSession
from src.modules.notifications.api.dependencies import (
    AppClock,
    CurrentViewer,
    FeedServiceDep,
    StreamTicketsDep,
    ensure_organization_visible,
)
from src.modules.notifications.api.schemas import (
    ApplicationUpdated,
    FeedItemRead,
    FeedPage,
    Heartbeat,
    ReadAllResult,
    StreamTicketRead,
    UnreadCount,
)
from src.modules.notifications.application import stream
from src.modules.notifications.application.ports import FeedFilter, FeedStore
from src.modules.notifications.application.stream import (
    StreamEvent,
    feed_events,
    parse_last_event_id,
)
from src.modules.notifications.infrastructure.repositories import SqlAlchemyFeedStore

router = APIRouter(prefix="/feed", tags=["feed"])

OrganizationFilter = Annotated[UUID | None, Query()]
ApplicationFilter = Annotated[UUID | None, Query()]


@router.get("", response_model=FeedPage)
async def list_feed(
    request: Request,
    session: DbSession,
    viewer: CurrentViewer,
    service: FeedServiceDep,
    organization_id: OrganizationFilter = None,
    application_id: ApplicationFilter = None,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FeedPage:
    """The viewer's feed, newest first: own records and, for bank staff, the
    back office records (`role:underwriter`)."""
    await ensure_organization_visible(request, session, viewer, organization_id)
    flt = FeedFilter(organization_id, application_id, unread_only)
    records, total = await service.page(viewer.recipients, flt, limit, offset)
    return FeedPage(
        items=[FeedItemRead.from_record(r) for r in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(
    request: Request,
    session: DbSession,
    viewer: CurrentViewer,
    service: FeedServiceDep,
    organization_id: OrganizationFilter = None,
    application_id: ApplicationFilter = None,
) -> UnreadCount:
    await ensure_organization_visible(request, session, viewer, organization_id)
    count = await service.unread_count(
        viewer.recipients, FeedFilter(organization_id, application_id)
    )
    return UnreadCount(count=count)


@router.post("/read-all", response_model=ReadAllResult)
async def read_all(
    request: Request,
    session: DbSession,
    viewer: CurrentViewer,
    service: FeedServiceDep,
    organization_id: OrganizationFilter = None,
    application_id: ApplicationFilter = None,
) -> ReadAllResult:
    await ensure_organization_visible(request, session, viewer, organization_id)
    updated = await service.mark_all_read(
        viewer.recipients, FeedFilter(organization_id, application_id)
    )
    return ReadAllResult(updated=updated)


@router.post("/stream-ticket", response_model=StreamTicketRead)
async def stream_ticket(
    viewer: CurrentViewer, tickets: StreamTicketsDep, clock: AppClock
) -> StreamTicketRead:
    """One-time ticket for GET /feed/stream (EventSource can't send the token)."""
    issued = await tickets.issue(viewer.account_id, viewer.roles)
    return StreamTicketRead(
        ticket=issued.ticket,
        expires_at=issued.expires_at,
        expires_in=max(int((issued.expires_at - clock.now()).total_seconds()), 0),
        stream_url=f"/feed/stream?ticket={issued.ticket}",
    )


def _encode(event: StreamEvent) -> ServerSentEvent:
    if event.event == "heartbeat":
        assert event.at is not None
        return ServerSentEvent(Heartbeat(at=event.at).model_dump_json(), event="heartbeat")
    assert event.record is not None
    if event.event == "feed_item":
        data = FeedItemRead.from_record(event.record).model_dump_json()
    else:
        item = event.record.item
        data = ApplicationUpdated(
            application_id=item.application_id,  # type: ignore[arg-type]
            organization_id=item.organization_id,
            item_id=item.id,
            type=item.type,
        ).model_dump_json()
    return ServerSentEvent(data, event=event.event, id=event.id)


@router.get("/stream", response_class=EventSourceResponse)
async def feed_stream(
    request: Request,
    tickets: StreamTicketsDep,
    clock: AppClock,
    ticket: Annotated[str, Query(min_length=1, max_length=128)],
    last_event_id: Annotated[str | None, Query(max_length=32)] = None,
    last_event_id_header: Annotated[
        str | None, Header(alias="Last-Event-ID", max_length=32)
    ] = None,
) -> EventSourceResponse:
    """SSE: `feed_item` (id = stream position), `application_updated`, `heartbeat`.
    The ticket is spent on connect: to reconnect, take a new ticket and pass the
    last received id as `last_event_id` (or the Last-Event-ID header)."""
    grant = await tickets.redeem(ticket)
    cursor = parse_last_event_id(last_event_id_header or last_event_id)
    session_factory = request.app.state.session_factory

    @asynccontextmanager
    async def open_store() -> AsyncIterator[FeedStore]:
        async with session_factory() as session:
            yield SqlAlchemyFeedStore(session)

    async def body() -> AsyncIterator[ServerSentEvent]:
        events = feed_events(
            open_store,
            grant.recipients,
            cursor,
            clock,
            poll_seconds=stream.POLL_INTERVAL_SECONDS,
            heartbeat_seconds=stream.HEARTBEAT_SECONDS,
            max_seconds=stream.MAX_STREAM_SECONDS,
        )
        async for event in events:
            yield _encode(event)

    # Heartbeats come from the generator as named events, so the library ping is off.
    return EventSourceResponse(body(), ping=0)


@router.post("/{item_id}/read", response_model=FeedItemRead)
async def read_item(item_id: UUID, viewer: CurrentViewer, service: FeedServiceDep) -> FeedItemRead:
    """Someone else's record is 404, as if it did not exist."""
    return FeedItemRead.from_record(await service.mark_read(viewer.recipients, item_id))
