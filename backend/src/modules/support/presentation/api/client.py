"""The client's tickets: `support.read` / `support.create` with the `own_only` policy."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from src.core.http.pagination import TOTAL_HEADER
from src.modules.support.application.dto.tickets import NewTicketDTO
from src.modules.support.domain.enums import TicketStatus
from src.modules.support.presentation.dependencies import (
    CanRead,
    CanWrite,
    CloseMyTicketDep,
    GetTicketDep,
    ListMyTicketsDep,
    OpenTicketDep,
    PostClientMessageDep,
)
from src.modules.support.presentation.schemas.tickets import (
    MessageCreate,
    TicketCreate,
    TicketListItem,
    TicketOut,
)

router = APIRouter(prefix="/support/tickets", tags=["support"])


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def open_ticket(data: TicketCreate, access: CanWrite, use_case: OpenTicketDep) -> TicketOut:
    """A question to the bank with its first message; it lands in the staff queue."""
    view = await use_case.execute(
        access,
        NewTicketDTO(
            subject=data.subject,
            text=data.text,
            organization_id=data.organization_id,
            application_id=data.application_id,
        ),
    )
    return TicketOut.model_validate(view)


@router.get("", response_model=list[TicketListItem])
async def list_my_tickets(
    response: Response,
    access: CanRead,
    use_case: ListMyTicketsDep,
    status_filter: Annotated[list[TicketStatus] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TicketListItem]:
    """The client's tickets, newest activity first. The total by the same filter is in the
    `X-Total-Count` header."""
    tickets, total = await use_case.execute(access, status_filter or [], limit, offset)
    response.headers[TOTAL_HEADER] = str(total)
    return [TicketListItem.model_validate(ticket) for ticket in tickets]


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_my_ticket(ticket_id: UUID, access: CanRead, use_case: GetTicketDep) -> TicketOut:
    """The ticket with the whole chat."""
    return TicketOut.model_validate(await use_case.execute(access, ticket_id))


@router.post("/{ticket_id}/messages", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def post_client_message(
    ticket_id: UUID, data: MessageCreate, access: CanWrite, use_case: PostClientMessageDep
) -> TicketOut:
    """A message into the client's ticket; a closed one is 409. A message into a
    resolved ticket takes it back to the employee who handled it."""
    return TicketOut.model_validate(await use_case.execute(access, ticket_id, data.text))


@router.post("/{ticket_id}/close", response_model=TicketOut)
async def close_my_ticket(
    ticket_id: UUID, access: CanWrite, use_case: CloseMyTicketDep
) -> TicketOut:
    """The question is settled: nobody writes into the ticket anymore."""
    return TicketOut.model_validate(await use_case.execute(access, ticket_id))
