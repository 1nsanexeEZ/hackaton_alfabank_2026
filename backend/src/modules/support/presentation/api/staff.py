"""The staff queue: `support.manage` (underwriters; the admin has everything)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from src.core.http.pagination import TOTAL_HEADER
from src.modules.support.application.dto.tickets import QueueScope
from src.modules.support.domain.enums import TicketStatus
from src.modules.support.presentation.dependencies import (
    CanManage,
    CloseTicketDep,
    GetTicketDep,
    ListQueueDep,
    PostStaffMessageDep,
    ReleaseTicketDep,
    ResolveTicketDep,
    TakeTicketDep,
)
from src.modules.support.presentation.schemas.tickets import (
    MessageCreate,
    TicketListItem,
    TicketOut,
)

router = APIRouter(prefix="/support/queue", tags=["support"])


@router.get("", response_model=list[TicketListItem])
async def list_queue(
    response: Response,
    access: CanManage,
    use_case: ListQueueDep,
    status_filter: Annotated[list[TicketStatus] | None, Query(alias="status")] = None,
    scope: Annotated[
        QueueScope,
        Query(description="all — every ticket; unassigned — nobody took it; mine — taken by me"),
    ] = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TicketListItem]:
    """Tickets of all clients, newest activity first. The total by the same filter is in the
    `X-Total-Count` header."""
    tickets, total = await use_case.execute(access, status_filter or [], scope, limit, offset)
    response.headers[TOTAL_HEADER] = str(total)
    return [TicketListItem.model_validate(ticket) for ticket in tickets]


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(ticket_id: UUID, access: CanManage, use_case: GetTicketDep) -> TicketOut:
    return TicketOut.model_validate(await use_case.execute(access, ticket_id))


@router.post("/{ticket_id}/take", response_model=TicketOut)
async def take_ticket(ticket_id: UUID, access: CanManage, use_case: TakeTicketDep) -> TicketOut:
    """The ticket becomes the caller's. Already taken (by anyone) — 409 `already_taken`."""
    return TicketOut.model_validate(await use_case.execute(access, ticket_id))


@router.post("/{ticket_id}/release", response_model=TicketOut)
async def release_ticket(
    ticket_id: UUID, access: CanManage, use_case: ReleaseTicketDep
) -> TicketOut:
    """Back to the queue: anyone may take it again."""
    return TicketOut.model_validate(await use_case.execute(access, ticket_id))


@router.post("/{ticket_id}/messages", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def post_staff_message(
    ticket_id: UUID, data: MessageCreate, access: CanManage, use_case: PostStaffMessageDep
) -> TicketOut:
    """An answer to the client. Only the employee who took the ticket (the admin —
    in any taken ticket); not taken — 409 `not_taken`, taken by another — 403."""
    return TicketOut.model_validate(await use_case.execute(access, ticket_id, data.text))


@router.post("/{ticket_id}/resolve", response_model=TicketOut)
async def resolve_ticket(
    ticket_id: UUID, access: CanManage, use_case: ResolveTicketDep
) -> TicketOut:
    """The question is answered; the client may still write and reopen it."""
    return TicketOut.model_validate(await use_case.execute(access, ticket_id))


@router.post("/{ticket_id}/close", response_model=TicketOut)
async def close_ticket(ticket_id: UUID, access: CanManage, use_case: CloseTicketDep) -> TicketOut:
    """Final: nobody writes into the ticket anymore."""
    return TicketOut.model_validate(await use_case.execute(access, ticket_id))
