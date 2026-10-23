"""Personal news as the use cases return them."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NewsItemDTO:
    id: UUID
    title: str
    body: str
    published_at: datetime
    # Why the item was picked for this company ("ОКВЭД 56", "продукт OVERDRAFT").
    relevance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ViewerNewsDTO:
    """A personal news item with the viewer's read mark."""

    news: NewsItemDTO
    read: bool
