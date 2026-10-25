from typing import cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.core.exceptions.exceptions import NotFoundError
from src.modules.support.application.dto.tickets import TicketQuery
from src.modules.support.application.interfaces.repositories import TicketRepository
from src.modules.support.domain.ticket import SupportTicket
from src.modules.support.domain.value_objects import TicketNumber
from src.modules.support.infrastructure.database.models import NUMBER_SEQUENCE, TicketRecord
from src.modules.support.infrastructure.repositories.mappers import apply, new_record, to_domain


def _visible(stmt: Select[TicketRecord], access: AccessContext) -> Select[TicketRecord]:
    """The caller's row policies: a client sees only own tickets (`own_only`)."""
    return cast(Select[TicketRecord], apply_access_context(stmt, TicketRecord, access))


class SqlAlchemyTicketRepository(TicketRepository):
    """Keeps the rows it loaded, so `save` updates them in place and the
    `version` column guards against a concurrent writer."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._records: dict[UUID, TicketRecord] = {}

    async def next_number(self, year: int) -> TicketNumber:
        if self._session.get_bind().dialect.name == "postgresql":
            sequence = await self._session.scalar(select(NUMBER_SEQUENCE.next_value()))
        else:  # tests on SQLite: no sequences, no concurrency
            count = await self._session.scalar(select(func.count()).select_from(TicketRecord))
            sequence = (count or 0) + 1
        return TicketNumber.issue(year, int(sequence or 0))

    async def add(self, ticket: SupportTicket) -> None:
        record = new_record(ticket)
        self._session.add(record)
        await self._session.flush()
        self._remember(ticket, record)

    async def get(self, ticket_id: UUID, access: AccessContext | None = None) -> SupportTicket:
        stmt = select(TicketRecord).where(TicketRecord.id == ticket_id)
        if access is not None:
            stmt = _visible(stmt, access)
        record = (await self._session.scalars(stmt)).one_or_none()
        if record is None:
            raise NotFoundError("Ticket not found")
        ticket = to_domain(record)
        self._records[ticket.id] = record
        return ticket

    async def save(self, ticket: SupportTicket) -> None:
        record = self._records.get(ticket.id)
        if record is None:
            raise RuntimeError("Save only a ticket loaded by this repository")
        apply(ticket, record)
        await self._session.flush()
        self._remember(ticket, record)

    async def search(self, access: AccessContext, query: TicketQuery) -> list[SupportTicket]:
        stmt = _visible(select(TicketRecord), access)
        if query.statuses:
            stmt = stmt.where(TicketRecord.status.in_([s.value for s in query.statuses]))
        if query.unassigned:
            stmt = stmt.where(TicketRecord.assignee_id.is_(None))
        if query.assignee_id is not None:
            stmt = stmt.where(TicketRecord.assignee_id == query.assignee_id)
        stmt = stmt.order_by(TicketRecord.updated_at.desc(), TicketRecord.id)
        records = (await self._session.scalars(stmt.limit(query.limit).offset(query.offset))).all()
        return [to_domain(record) for record in records]

    def _remember(self, ticket: SupportTicket, record: TicketRecord) -> None:
        self._records[ticket.id] = record
        ticket.version = record.version
