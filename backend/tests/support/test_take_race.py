"""Two employees take one ticket at the same moment: the version column lets
only one of them win, the other one gets 409."""

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.access.access_context import AccessContext
from src.core.access.permissions import Permissions
from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import ConflictError
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.modules.support.application.interfaces.repositories import TicketChangedError
from src.modules.support.application.use_cases.staff import TakeTicketUseCase
from src.modules.support.domain.ticket import SupportTicket
from src.modules.support.domain.value_objects import Staff, TicketNumber
from src.modules.support.infrastructure.adapters.unit_of_work import SupportUnitOfWork
from src.modules.support.infrastructure.repositories.tickets import SqlAlchemyTicketRepository
from tests.fakes.builders import NOW
from tests.fakes.identity_facade import FakeIdentityFacade

Sessions = async_sessionmaker[AsyncSession]


def staff_access(account_id: UUID) -> AccessContext:
    return AccessContext(
        user_id=account_id,
        permission=Permissions.SUPPORT_MANAGE,
        granted_permissions=(Permissions.SUPPORT_MANAGE.value,),
    )


async def open_ticket(sessions: Sessions) -> UUID:
    async with sessions() as session:
        repository = SqlAlchemyTicketRepository(session)
        ticket = SupportTicket.open(
            id=uuid4(),
            number=TicketNumber.issue(2026, 1),
            author_id=uuid4(),
            subject="Вопрос",
            text="Текст",
            message_id=uuid4(),
            now=NOW,
        )
        await repository.add(ticket)
        await session.commit()
        return ticket.id


async def take_in_own_transaction(sessions: Sessions, ticket_id: UUID, staff: UUID) -> None:
    async with sessions() as session:
        repository = SqlAlchemyTicketRepository(session)
        ticket = await repository.get(ticket_id)
        ticket.take(Staff(staff), NOW)
        await repository.save(ticket)
        await session.commit()


class RacingRepository(SqlAlchemyTicketRepository):
    """Right before the first write, somebody else commits a change of the same
    ticket in a transaction of their own."""

    def __init__(self, session: AsyncSession, rival: Callable[[], Awaitable[None]]) -> None:
        super().__init__(session)
        self._rival: Callable[[], Awaitable[None]] | None = rival

    async def save(self, ticket: SupportTicket) -> None:
        if self._rival is not None:
            rival, self._rival = self._rival, None
            await rival()
        await super().save(ticket)


async def assignee(sessions: Sessions, ticket_id: UUID) -> UUID | None:
    async with sessions() as session:
        return (await SqlAlchemyTicketRepository(session).get(ticket_id)).assignee_id


async def test_the_stale_writer_is_rolled_back_with_409(session_factory: Sessions) -> None:
    ticket_id = await open_ticket(session_factory)
    anna, boris = uuid4(), uuid4()

    async with session_factory() as session:
        repository = SqlAlchemyTicketRepository(session)
        with pytest.raises(TicketChangedError) as error:
            async with SupportUnitOfWork(session) as uow:
                ticket = await repository.get(ticket_id)  # version 1
                await take_in_own_transaction(session_factory, ticket_id, anna)  # now 2
                ticket.take(Staff(boris), NOW)
                await repository.save(ticket)
                await uow.commit()

    assert error.value.status_code == 409
    assert error.value.details == {"code": "version_conflict"}
    assert await assignee(session_factory, ticket_id) == anna


async def test_the_loser_of_the_take_race_gets_already_taken(session_factory: Sessions) -> None:
    ticket_id = await open_ticket(session_factory)
    anna, boris = uuid4(), uuid4()

    async with session_factory() as session:
        use_case = TakeTicketUseCase(
            SupportUnitOfWork(session),
            RacingRepository(
                session, lambda: take_in_own_transaction(session_factory, ticket_id, anna)
            ),
            SqlAlchemyOutboxWriter(session, "support", FrozenClock(NOW)),
            FakeIdentityFacade(),
            FrozenClock(NOW),
        )
        with pytest.raises(ConflictError) as error:
            await use_case.execute(staff_access(boris), ticket_id)

    assert error.value.details == {"code": "already_taken", "assignee_id": str(anna)}
    assert await assignee(session_factory, ticket_id) == anna


async def test_a_concurrent_change_of_another_kind_does_not_stop_the_take(
    session_factory: Sessions,
) -> None:
    ticket_id = await open_ticket(session_factory)
    boris = uuid4()

    async def client_writes() -> None:
        async with session_factory() as session:
            repository = SqlAlchemyTicketRepository(session)
            ticket = await repository.get(ticket_id)
            ticket.post_client_message(ticket.author_id, uuid4(), "Дополнение", NOW)
            await repository.save(ticket)
            await session.commit()

    async with session_factory() as session:
        use_case = TakeTicketUseCase(
            SupportUnitOfWork(session),
            RacingRepository(session, client_writes),
            SqlAlchemyOutboxWriter(session, "support", FrozenClock(NOW)),
            FakeIdentityFacade(),
            FrozenClock(NOW),
        )
        view = await use_case.execute(staff_access(boris), ticket_id)

    assert view.assignee_id == boris
    assert [m.text for m in view.messages] == ["Текст", "Дополнение"]
