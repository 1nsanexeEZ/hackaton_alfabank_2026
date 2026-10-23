"""Use cases of the feed: who sees what, reading, read marks."""

from collections.abc import Sequence
from uuid import UUID

from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError
from src.core.uow import UnitOfWork
from src.modules.notifications.application.ports import FeedFilter, FeedRecord, FeedStore
from src.modules.notifications.domain.feed import UNDERWRITERS, Recipient

# Holders of these permissions are bank staff: they read the back office feed
# (`role:underwriter`) and may look at any company.
BANK_PERMISSIONS = frozenset({Permissions.BACKOFFICE_READ.value, Permissions.ADMIN.value})
# Identity roles of bank staff, for the facade that knows only the account id.
BANK_ROLE_NAMES = frozenset({"underwriter", "admin"})


def is_bank_staff(permissions: Sequence[str]) -> bool:
    return not BANK_PERMISSIONS.isdisjoint(permissions)


def viewer_recipients(account_id: UUID, bank_staff: bool) -> tuple[Recipient, ...]:
    own = Recipient.account(account_id)
    return (own, UNDERWRITERS) if bank_staff else (own,)


class FeedService:
    def __init__(self, store: FeedStore, uow: UnitOfWork, clock: Clock) -> None:
        self._store = store
        self._uow = uow
        self._clock = clock

    async def page(
        self, recipients: Sequence[Recipient], flt: FeedFilter, limit: int, offset: int
    ) -> tuple[list[FeedRecord], int]:
        return await self._store.page(recipients, flt, limit, offset)

    async def unread_count(self, recipients: Sequence[Recipient], flt: FeedFilter) -> int:
        return await self._store.unread_count(recipients, flt)

    async def mark_read(self, recipients: Sequence[Recipient], item_id: UUID) -> FeedRecord:
        async with self._uow:
            record = await self._store.mark_read(recipients, item_id, self._clock.now())
            if record is None:
                raise NotFoundError("Feed item not found")
            await self._uow.commit()
        return record

    async def mark_all_read(self, recipients: Sequence[Recipient], flt: FeedFilter) -> int:
        async with self._uow:
            updated = await self._store.mark_all_read(recipients, flt, self._clock.now())
            await self._uow.commit()
        return updated
