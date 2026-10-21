from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.notifications.application.ports import FeedRecord
from src.notifications.domain.news import RankedNews


class FeedItemRead(BaseModel):
    """Title and body are HTML-escaped text: substituted values never carry markup."""

    id: UUID
    # Stream position, the same as the SSE event id: pass the largest one as
    # last_event_id to continue the live feed right after this page.
    seq: int
    type: str
    audience: str
    title: str
    body: str
    link: str | None
    priority: str
    action_required: bool
    organization_id: UUID | None
    application_id: UUID | None
    created_at: datetime
    read_at: datetime | None

    @classmethod
    def from_record(cls, record: FeedRecord) -> "FeedItemRead":
        item = record.item
        return cls(
            id=item.id,
            seq=record.seq,
            type=item.type,
            audience=record.audience,
            title=item.title,
            body=item.body,
            link=item.link,
            priority=item.priority,
            action_required=item.action_required,
            organization_id=item.organization_id,
            application_id=item.application_id,
            created_at=item.created_at,
            read_at=item.read_at,
        )


class FeedPage(BaseModel):
    items: list[FeedItemRead]
    total: int
    limit: int
    offset: int


class UnreadCount(BaseModel):
    count: int


class ReadAllResult(BaseModel):
    updated: int


class StreamTicketRead(BaseModel):
    ticket: str
    expires_at: datetime
    expires_in: int
    stream_url: str


class ApplicationUpdated(BaseModel):
    application_id: UUID
    organization_id: UUID | None
    item_id: UUID
    type: str


class Heartbeat(BaseModel):
    at: datetime


class NewsRead(BaseModel):
    id: UUID
    title: str
    body: str
    published_at: datetime
    # Why the article was picked for the company ("ОКВЭД 56 — общепит").
    relevance: list[str]
    read: bool

    @classmethod
    def from_ranked(cls, ranked: RankedNews, read: bool) -> "NewsRead":
        article = ranked.article
        return cls(
            id=article.id,
            title=article.title,
            body=article.body,
            published_at=article.published_at,
            relevance=list(ranked.relevance),
            read=read,
        )
