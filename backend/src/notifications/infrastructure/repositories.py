"""SQLAlchemy implementations of the notifications storage ports."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import ColumnElement, and_, delete, false, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.notifications.application.ports import FeedFilter, FeedRecord, StreamGrant
from src.notifications.domain.feed import Delivery, FeedEntry, Recipient
from src.notifications.domain.news import NewsArticle
from src.notifications.facade import FeedItemDTO
from src.notifications.infrastructure.models import FeedItem, NewsItem, NewsRead, StreamTicket


def aware(moment: datetime) -> datetime:
    """SQLite returns naive datetimes; everything is stored in UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


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


def to_record(row: FeedItem) -> FeedRecord:
    item = FeedItemDTO(
        id=row.id,
        type=cast(Any, row.type),
        title=row.title,
        body=row.body,
        link=row.link,
        priority=cast(Any, row.priority),
        action_required=row.action_required,
        organization_id=row.organization_id,
        application_id=row.application_id,
        created_at=aware(row.created_at),
        read_at=aware(row.read_at) if row.read_at else None,
    )
    return FeedRecord(
        item=item,
        seq=row.seq,
        audience=cast(Any, row.audience),
        recipient=Recipient(cast(Any, row.recipient_type), row.recipient_id),
    )


class SqlAlchemyFeedStore:
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
        for recipient in pending:
            row = None
            if delivery.replace_group and entry.group_key is not None:
                row = await self._group_row(recipient, entry.group_key)
            if row is None:
                row = FeedItem(
                    recipient_type=recipient.type,
                    recipient_id=recipient.id,
                    created_at=now,
                )
                self._session.add(row)
            self._fill(row, entry, source_id, source_type, seq, now)
            seq += 1
        await self._session.flush()
        return len(pending)

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


def to_article(row: NewsItem) -> NewsArticle:
    return NewsArticle(
        id=row.id,
        slug=row.slug,
        title=row.title,
        body=row.body,
        published_at=aware(row.published_at),
        okved_prefixes=tuple(row.okved_prefixes or ()),
        product_codes=tuple(row.product_codes or ()),
        legal_forms=tuple(row.legal_forms or ()),
        is_general=row.is_general,
    )


class SqlAlchemyNewsStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def published(self, now: datetime) -> list[NewsArticle]:
        stmt = select(NewsItem).where(NewsItem.published_at <= now).order_by(NewsItem.slug)
        return [to_article(row) for row in (await self._session.scalars(stmt)).all()]

    async def exists(self, news_id: UUID) -> bool:
        return await self._session.get(NewsItem, news_id) is not None

    async def read_ids(self, account_id: UUID, news_ids: Sequence[UUID]) -> set[UUID]:
        if not news_ids:
            return set()
        stmt = select(NewsRead.news_id).where(
            NewsRead.account_id == account_id, NewsRead.news_id.in_(list(news_ids))
        )
        return set((await self._session.scalars(stmt)).all())

    async def mark_read(self, news_id: UUID, account_id: UUID, now: datetime) -> None:
        if await self._session.get(NewsRead, (news_id, account_id)) is None:
            self._session.add(NewsRead(news_id=news_id, account_id=account_id, read_at=now))
            await self._session.flush()

    async def upsert(self, article: NewsArticle, now: datetime) -> bool:
        """Seed: insert by slug or refresh the text and tags. True when inserted;
        the publication date of an existing article is kept."""
        row = (
            await self._session.scalars(select(NewsItem).where(NewsItem.slug == article.slug))
        ).one_or_none()
        inserted = row is None
        if row is None:
            row = NewsItem(
                id=article.id, slug=article.slug, published_at=article.published_at, created_at=now
            )
            self._session.add(row)
        row.title = article.title
        row.body = article.body
        row.okved_prefixes = list(article.okved_prefixes)
        row.product_codes = list(article.product_codes)
        row.legal_forms = list(article.legal_forms)
        row.is_general = article.is_general
        row.updated_at = now
        await self._session.flush()
        return inserted


class SqlAlchemyTicketStore:
    # Used and expired tickets are kept this long, then removed on the next issue.
    RETENTION_SECONDS = 3600

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        ticket_hash: str,
        account_id: UUID,
        roles: Sequence[str],
        expires_at: datetime,
        now: datetime,
    ) -> None:
        cutoff = datetime.fromtimestamp(now.timestamp() - self.RETENTION_SECONDS, UTC)
        await self._session.execute(delete(StreamTicket).where(StreamTicket.expires_at < cutoff))
        self._session.add(
            StreamTicket(
                ticket_hash=ticket_hash,
                account_id=account_id,
                roles=list(roles),
                expires_at=expires_at,
                created_at=now,
            )
        )
        await self._session.flush()

    async def redeem(self, ticket_hash: str, now: datetime) -> StreamGrant | None:
        row = (
            await self._session.scalars(
                select(StreamTicket).where(StreamTicket.ticket_hash == ticket_hash)
            )
        ).one_or_none()
        if row is None or row.used_at is not None or aware(row.expires_at) <= now:
            return None
        # Conditional update: of two concurrent connections only one wins the ticket.
        result = await self._session.execute(
            update(StreamTicket)
            .where(StreamTicket.id == row.id, StreamTicket.used_at.is_(None))
            .values(used_at=now)
        )
        if getattr(result, "rowcount", 0) != 1:
            return None
        recipients = (Recipient.account(row.account_id),) + tuple(
            Recipient.role(role) for role in row.roles or ()
        )
        return StreamGrant(account_id=row.account_id, recipients=recipients)
