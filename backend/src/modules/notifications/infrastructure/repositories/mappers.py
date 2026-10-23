"""Table rows -> domain records of notifications."""

from datetime import UTC, datetime
from typing import Any, cast

from src.modules.notifications.domain.feed import FeedRecord, Recipient
from src.modules.notifications.domain.news import NewsArticle
from src.modules.notifications.infrastructure.database.models import FeedItem, NewsItem


def aware(moment: datetime) -> datetime:
    """SQLite returns naive datetimes; everything is stored in UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def to_record(row: FeedItem) -> FeedRecord:
    return FeedRecord(
        id=row.id,
        seq=row.seq,
        recipient=Recipient(cast(Any, row.recipient_type), row.recipient_id),
        audience=cast(Any, row.audience),
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
