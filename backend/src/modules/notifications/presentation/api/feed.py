from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query
from sse_starlette import EventSourceResponse, ServerSentEvent

from src.modules.notifications.application.dto.feed import FeedFilter
from src.modules.notifications.application.dto.stream import StreamEvent
from src.modules.notifications.application.use_cases.stream import parse_last_event_id
from src.modules.notifications.presentation.dependencies import (
    AppClock,
    CountUnreadDep,
    CurrentViewer,
    IssueStreamTicketDep,
    ListFeedDep,
    MarkAllFeedReadDep,
    MarkFeedItemReadDep,
    OrganizationVisibilityDep,
    RedeemStreamTicketDep,
    StreamFeedDep,
    ViewerOrganizationsDep,
)
from src.modules.notifications.presentation.schemas.feed import (
    ApplicationUpdated,
    FeedItemRead,
    FeedPage,
    Heartbeat,
    ReadAllResult,
    StreamTicketRead,
    UnreadCount,
)

router = APIRouter(prefix="/feed", tags=["feed"])

OrganizationFilter = Annotated[UUID | None, Query()]
ApplicationFilter = Annotated[UUID | None, Query()]


@router.get("", response_model=FeedPage)
async def list_feed(
    viewer: CurrentViewer,
    visibility: OrganizationVisibilityDep,
    organizations: ViewerOrganizationsDep,
    feed: ListFeedDep,
    organization_id: OrganizationFilter = None,
    application_id: ApplicationFilter = None,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FeedPage:
    """The viewer's feed, newest first: own records and, for bank staff, the
    back office records (`role:underwriter`). A client sees the records of the
    companies where they are a member now: after leaving a company its records
    are gone (own support tickets stay)."""
    await visibility.execute(viewer.account_id, viewer.bank_staff, organization_id)
    scope = await organizations.execute(viewer.account_id, viewer.bank_staff)
    flt = FeedFilter(organization_id, application_id, unread_only, scope)
    records, total = await feed.execute(viewer.recipients, flt, limit, offset)
    return FeedPage(
        items=[FeedItemRead.from_record(r) for r in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(
    viewer: CurrentViewer,
    visibility: OrganizationVisibilityDep,
    organizations: ViewerOrganizationsDep,
    count_unread: CountUnreadDep,
    organization_id: OrganizationFilter = None,
    application_id: ApplicationFilter = None,
) -> UnreadCount:
    await visibility.execute(viewer.account_id, viewer.bank_staff, organization_id)
    scope = await organizations.execute(viewer.account_id, viewer.bank_staff)
    count = await count_unread.execute(
        viewer.recipients, FeedFilter(organization_id, application_id, organizations=scope)
    )
    return UnreadCount(count=count)


@router.post("/read-all", response_model=ReadAllResult)
async def read_all(
    viewer: CurrentViewer,
    visibility: OrganizationVisibilityDep,
    organizations: ViewerOrganizationsDep,
    mark_all_read: MarkAllFeedReadDep,
    organization_id: OrganizationFilter = None,
    application_id: ApplicationFilter = None,
) -> ReadAllResult:
    await visibility.execute(viewer.account_id, viewer.bank_staff, organization_id)
    scope = await organizations.execute(viewer.account_id, viewer.bank_staff)
    updated = await mark_all_read.execute(
        viewer.recipients, FeedFilter(organization_id, application_id, organizations=scope)
    )
    return ReadAllResult(updated=updated)


@router.post("/stream-ticket", response_model=StreamTicketRead)
async def stream_ticket(
    viewer: CurrentViewer, issue_ticket: IssueStreamTicketDep, clock: AppClock
) -> StreamTicketRead:
    """One-time ticket for GET /feed/stream (EventSource can't send the token)."""
    issued = await issue_ticket.execute(viewer.account_id, viewer.roles)
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
    redeem_ticket: RedeemStreamTicketDep,
    stream_feed: StreamFeedDep,
    ticket: Annotated[str, Query(min_length=1, max_length=128)],
    last_event_id: Annotated[str | None, Query(max_length=32)] = None,
    last_event_id_header: Annotated[
        str | None, Header(alias="Last-Event-ID", max_length=32)
    ] = None,
) -> EventSourceResponse:
    """SSE: `feed_item` (id = stream position), `application_updated`, `heartbeat`.
    The ticket is spent on connect: to reconnect, take a new ticket and pass the
    last received id as `last_event_id` (or the Last-Event-ID header)."""
    grant = await redeem_ticket.execute(ticket)
    cursor = parse_last_event_id(last_event_id_header or last_event_id)

    async def body() -> AsyncIterator[ServerSentEvent]:
        async for event in stream_feed.execute(grant.recipients, cursor):
            yield _encode(event)

    # Heartbeats come from the generator as named events, so the library ping is off.
    return EventSourceResponse(body(), ping=0)


@router.post("/{item_id}/read", response_model=FeedItemRead)
async def read_item(
    item_id: UUID,
    viewer: CurrentViewer,
    organizations: ViewerOrganizationsDep,
    mark_read: MarkFeedItemReadDep,
) -> FeedItemRead:
    """Someone else's record, or one of a company the viewer has left, is 404,
    as if it did not exist."""
    scope = await organizations.execute(viewer.account_id, viewer.bank_staff)
    record = await mark_read.execute(viewer.recipients, item_id, FeedFilter(organizations=scope))
    return FeedItemRead.from_record(record)
