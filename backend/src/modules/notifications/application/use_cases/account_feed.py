"""The feed of an account for neighbours (the dashboard in bff). Only the account
id is known, so whether the account also reads the back office feed is asked
from identity. No access checks: the caller checks the company."""

from uuid import UUID

from src.modules.notifications.application.dto.feed import FeedFilter, FeedItemDTO
from src.modules.notifications.application.interfaces.neighbours import Neighbours
from src.modules.notifications.application.interfaces.repositories import FeedStore
from src.modules.notifications.application.mappers.feed import feed_item_dto
from src.modules.notifications.domain.feed import Recipient
from src.modules.notifications.domain.viewers import BANK_ROLE_NAMES, viewer_recipients


async def account_recipients(neighbours: Neighbours, account_id: UUID) -> tuple[Recipient, ...]:
    role = await neighbours.account_role(account_id)
    return viewer_recipients(account_id, bank_staff=role in BANK_ROLE_NAMES)


class CountAccountUnreadUseCase:
    def __init__(self, store: FeedStore, neighbours: Neighbours) -> None:
        self._store = store
        self._neighbours = neighbours

    async def execute(self, account_id: UUID, organization_id: UUID | None = None) -> int:
        return await self._store.unread_count(
            await account_recipients(self._neighbours, account_id),
            FeedFilter(organization_id=organization_id),
        )


class LatestAccountFeedUseCase:
    def __init__(self, store: FeedStore, neighbours: Neighbours) -> None:
        self._store = store
        self._neighbours = neighbours

    async def execute(
        self,
        account_id: UUID,
        organization_id: UUID | None = None,
        application_id: UUID | None = None,
        limit: int = 10,
    ) -> list[FeedItemDTO]:
        records, _ = await self._store.page(
            await account_recipients(self._neighbours, account_id),
            FeedFilter(organization_id=organization_id, application_id=application_id),
            limit=max(limit, 0),
            offset=0,
        )
        return [feed_item_dto(record) for record in records]
