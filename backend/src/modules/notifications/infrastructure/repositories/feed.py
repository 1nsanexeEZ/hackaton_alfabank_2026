from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import ColumnElement, and_, false, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.application.dto.feed import FeedFilter
from src.modules.notifications.application.interfaces.repositories import FeedStore
from src.modules.notifications.domain.feed import Delivery, FeedEntry, FeedRecord, Recipient
from src.modules.notifications.infrastructure.database.models import FeedItem
from src.modules.notifications.infrastructure.repositories.mappers import to_record


def _recipients_clause(recipients: Sequence[Recipient]) -> ColumnElement[bool]:
    if not recipients:
        return false()
    return or_(
        *(
            and_(FeedItem.recipient_type == r.type, FeedItem.recipient_id == r.id)
            for r in recipients
        )
    )


def _filter_clauses(flt: FeedFilter) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = []
    if flt.organization_id is not None:
        clauses.append(FeedItem.organization_id == flt.organization_id)
    if flt.application_id is not None:
        clauses.append(FeedItem.application_id == flt.application_id)
    if flt.unread_only:
        clauses.append(FeedItem.read_at.is_(None))
    return clauses


class SqlAlchemyFeedStore(FeedStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- writing (Kafka handler, no commit) ------------------------------------

    async def _next_seq(self) -> int:
        """Next stream position. Two writers taking the same value collide on the
        unique constraint and the handler is retried, so positions become visible
        in increasing order — what an SSE cursor needs."""
        current = await self._session.scalar(select(func.max(FeedItem.seq)))
        return (current or 0) + 1

    async def append(
        self, delivery: Delivery, event_id: UUID, source_type: str, now: datetime
    ) -> int:
        entry = delivery.entry
        source_id = entry.source_id(event_id)
        done = {
            (row.recipient_type, row.recipient_id)
            for row in (
                await self._session.execute(
                    select(FeedItem.recipient_type, FeedItem.recipient_id).where(
                        FeedItem.source_event_id == source_id
                    )
                )
            )
        }
        pending = [r for r in dict.fromkeys(delivery.recipients) if (r.type, r.id) not in done]
        if not pending:
            return 0
        seq = await self._next_seq()
        written = 0
        for recipient in pending:
            row = None
            if delivery.replace_group and entry.group_key is not None:
                row = await self._group_row(recipient, entry.group_key)
            if delivery.only_existing and (
                row is None or (row.title, row.body) == (entry.title, entry.body)
            ):
                continue
            if row is None:
                row = FeedItem(
                    recipient_type=recipient.type,
                    recipient_id=recipient.id,
                    created_at=now,
                )
                self._session.add(row)
            self._fill(row, entry, source_id, source_type, seq, now)
            seq += 1
            written += 1
        await self._session.flush()
        return written

    async def _group_row(self, recipient: Recipient, group_key: str) -> FeedItem | None:
        stmt = (
            select(FeedItem)
            .where(
                FeedItem.recipient_type == recipient.type,
                FeedItem.recipient_id == recipient.id,
                FeedItem.group_key == group_key,
            )
            .order_by(FeedItem.seq.desc())
            .limit(1)
        )
        return (await self._session.scalars(stmt)).first()

    @staticmethod
    def _fill(
        row: FeedItem, entry: FeedEntry, source_id: UUID, source_type: str, seq: int, now: datetime
    ) -> None:
        """A replaced record is news again: new position, time and unread."""
        row.seq = seq
        row.source_event_id = source_id
        row.source_type = source_type
        row.audience = entry.audience
        row.type = entry.type
        row.title = entry.title[:255]
        row.body = entry.body
        row.link = entry.link
        row.priority = entry.priority
        row.action_required = entry.action_required
        row.organization_id = entry.organization_id
        row.application_id = entry.application_id
        row.group_key = entry.group_key
        row.read_at = None
        row.created_at = now
        row.updated_at = now

    async def resolve_group(self, group_key: str, now: datetime) -> int:
        result = await self._session.execute(
            update(FeedItem)
            .where(FeedItem.group_key == group_key, FeedItem.action_required.is_(True))
            .values(action_required=False, updated_at=now)
        )
        return cast(int, getattr(result, "rowcount", 0) or 0)

    # --- reading ---------------------------------------------------------------

    async def page(
        self, recipients: Sequence[Recipient], flt: FeedFilter, limit: int, offset: int
    ) -> tuple[list[FeedRecord], int]:
        where = [_recipients_clause(recipients), *_filter_clauses(flt)]
        total = await self._session.scalar(select(func.count()).select_from(FeedItem).where(*where))
        stmt = (
            select(FeedItem).where(*where).order_by(FeedItem.seq.desc()).limit(limit).offset(offset)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [to_record(row) for row in rows], int(total or 0)

    async def unread_count(self, recipients: Sequence[Recipient], flt: FeedFilter) -> int:
        where = [
            _recipients_clause(recipients),
            *_filter_clauses(flt),
            FeedItem.read_at.is_(None),
        ]
        count = await self._session.scalar(select(func.count()).select_from(FeedItem).where(*where))
        return int(count or 0)

    async def mark_read(
        self, recipients: Sequence[Recipient], item_id: UUID, now: datetime
    ) -> FeedRecord | None:
        stmt = select(FeedItem).where(FeedItem.id == item_id, _recipients_clause(recipients))
        row = (await self._session.scalars(stmt)).one_or_none()
        if row is None:
            return None
        if row.read_at is None:
            row.read_at = now
            await self._session.flush()
        return to_record(row)

    async def mark_all_read(
        self, recipients: Sequence[Recipient], flt: FeedFilter, now: datetime
    ) -> int:
        result = await self._session.execute(
            update(FeedItem)
            .where(
                _recipients_clause(recipients),
                *_filter_clauses(flt),
                FeedItem.read_at.is_(None),
            )
            .values(read_at=now)
        )
        return cast(int, getattr(result, "rowcount", 0) or 0)

    async def latest_seq(self, recipients: Sequence[Recipient]) -> int:
        stmt = select(func.max(FeedItem.seq)).where(_recipients_clause(recipients))
        return int(await self._session.scalar(stmt) or 0)

    async def after(
        self, recipients: Sequence[Recipient], seq: int, limit: int
    ) -> list[FeedRecord]:
        stmt = (
            select(FeedItem)
            .where(_recipients_clause(recipients), FeedItem.seq > seq)
            .order_by(FeedItem.seq)
            .limit(limit)
        )
        return [to_record(row) for row in (await self._session.scalars(stmt)).all()]
