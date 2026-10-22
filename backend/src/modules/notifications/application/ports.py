"""Storage ports of the notifications use cases (implemented in infrastructure)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.notifications.domain.feed import Audience, Delivery, Recipient
from src.modules.notifications.domain.news import NewsArticle
from src.modules.notifications.facade import FeedItemDTO


@dataclass(frozen=True, slots=True)
class FeedRecord:
    item: FeedItemDTO
    # Stream position: the SSE event id.
    seq: int
    audience: Audience
    recipient: Recipient


@dataclass(frozen=True, slots=True)
class FeedFilter:
    organization_id: UUID | None = None
    application_id: UUID | None = None
    unread_only: bool = False


@dataclass(frozen=True, slots=True)
class StreamGrant:
    account_id: UUID
    recipients: tuple[Recipient, ...]


class FeedStore(Protocol):
    async def append(
        self, delivery: Delivery, event_id: UUID, source_type: str, now: datetime
    ) -> int:
        """Write the entry for every recipient that has none from this event yet;
        with `replace_group` the recipient's entry of the same group is replaced.
        Returns the number of records written."""
        ...

    async def resolve_group(self, group_key: str, now: datetime) -> int:
        """The entries of the group need no action anymore (a task was done)."""
        ...

    async def page(
        self, recipients: Sequence[Recipient], flt: FeedFilter, limit: int, offset: int
    ) -> tuple[list[FeedRecord], int]: ...

    async def unread_count(self, recipients: Sequence[Recipient], flt: FeedFilter) -> int: ...

    async def mark_read(
        self, recipients: Sequence[Recipient], item_id: UUID, now: datetime
    ) -> FeedRecord | None: ...

    async def mark_all_read(
        self, recipients: Sequence[Recipient], flt: FeedFilter, now: datetime
    ) -> int: ...

    async def latest_seq(self, recipients: Sequence[Recipient]) -> int: ...

    async def after(
        self, recipients: Sequence[Recipient], seq: int, limit: int
    ) -> list[FeedRecord]: ...


class NewsStore(Protocol):
    async def published(self, now: datetime) -> list[NewsArticle]: ...

    async def exists(self, news_id: UUID) -> bool: ...

    async def read_ids(self, account_id: UUID, news_ids: Sequence[UUID]) -> set[UUID]: ...

    async def mark_read(self, news_id: UUID, account_id: UUID, now: datetime) -> None: ...


class TicketStore(Protocol):
    async def add(
        self,
        ticket_hash: str,
        account_id: UUID,
        roles: Sequence[str],
        expires_at: datetime,
        now: datetime,
    ) -> None: ...

    async def redeem(self, ticket_hash: str, now: datetime) -> StreamGrant | None:
        """Marks the ticket used; None when unknown, used or expired."""
        ...
