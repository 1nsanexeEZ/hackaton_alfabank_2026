from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.messaging import topics
from src.core.messaging.contracts.applications import StartReview
from src.core.messaging.envelope import Envelope
from src.core.messaging.inbox import SqlAlchemyInboxGuard
from src.core.messaging.outbox import OutboxRecord, SqlAlchemyOutboxWriter


async def test_outbox_stores_full_envelope_in_the_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    application_id, command_id = uuid4(), uuid4()
    async with session_factory() as session:
        writer = SqlAlchemyOutboxWriter(session, "process", FrozenClock())
        event_id = await writer.add(
            StartReview(application_id=application_id, client_stage="Заявка принята"),
            key=application_id,
            correlation_id=application_id,
            causation_id=command_id,
        )
        await session.commit()

    async with session_factory() as session:
        record = (await session.execute(select(OutboxRecord))).scalar_one()
    assert record.event_id == event_id
    assert record.topic == topics.APPLICATIONS_COMMANDS
    assert record.key == str(application_id)
    assert record.message_type == "StartReview"
    assert record.published_at is None
    envelope = Envelope.model_validate(record.envelope)
    assert envelope.producer == "process"
    assert envelope.causation_id == command_id
    assert envelope.payload["client_stage"] == "Заявка принята"


async def test_outbox_record_disappears_with_rollback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        writer = SqlAlchemyOutboxWriter(session, "process", FrozenClock())
        application_id = uuid4()
        await writer.add(
            StartReview(application_id=application_id),
            key=application_id,
            correlation_id=application_id,
        )
        await session.rollback()
    async with session_factory() as session:
        assert (await session.execute(select(OutboxRecord))).first() is None


async def test_inbox_is_per_consumer(session_factory: async_sessionmaker[AsyncSession]) -> None:
    event_id = uuid4()
    async with session_factory() as session:
        inbox = SqlAlchemyInboxGuard(session, FrozenClock())
        assert not await inbox.seen("projector.read-models", event_id)
        await inbox.mark("projector.read-models", event_id)
        await session.commit()
    async with session_factory() as session:
        inbox = SqlAlchemyInboxGuard(session, FrozenClock())
        assert await inbox.seen("projector.read-models", event_id)
        assert not await inbox.seen("notifications.feed", event_id)
