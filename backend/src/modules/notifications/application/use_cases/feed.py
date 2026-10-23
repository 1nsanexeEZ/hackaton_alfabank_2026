"""Use cases of the feed: reading and read marks of the viewer's recipients."""

from collections.abc import Sequence
from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError
from src.core.uow import UnitOfWork
from src.modules.notifications.application.dto.feed import FeedFilter, FeedRecordDTO
from src.modules.notifications.application.interfaces.repositories import FeedStore
from src.modules.notifications.application.mappers.feed import feed_record_dto
from src.modules.notifications.domain.feed import Recipient


class ListFeedUseCase:
    def __init__(self, store: FeedStore) -> None:
        self._store = store

    async def execute(
        self, recipients: Sequence[Recipient], flt: FeedFilter, limit: int, offset: int
    ) -> tuple[list[FeedRecordDTO], int]:
        records, total = await self._store.page(recipients, flt, limit, offset)
        return [feed_record_dto(record) for record in records], total


class CountUnreadUseCase:
    def __init__(self, store: FeedStore) -> None:
        self._store = store

    async def execute(self, recipients: Sequence[Recipient], flt: FeedFilter) -> int:
        return await self._store.unread_count(recipients, flt)


class MarkFeedItemReadUseCase:
    def __init__(self, store: FeedStore, uow: UnitOfWork, clock: Clock) -> None:
        self._store = store
        self._uow = uow
        self._clock = clock

    async def execute(self, recipients: Sequence[Recipient], item_id: UUID) -> FeedRecordDTO:
        async with self._uow:
            record = await self._store.mark_read(recipients, item_id, self._clock.now())
            if record is None:
                raise NotFoundError("Feed item not found")
            await self._uow.commit()
        return feed_record_dto(record)


class MarkAllFeedReadUseCase:
    def __init__(self, store: FeedStore, uow: UnitOfWork, clock: Clock) -> None:
        self._store = store
        self._uow = uow
        self._clock = clock

    async def execute(self, recipients: Sequence[Recipient], flt: FeedFilter) -> int:
        async with self._uow:
            updated = await self._store.mark_all_read(recipients, flt, self._clock.now())
            await self._uow.commit()
        return updated
