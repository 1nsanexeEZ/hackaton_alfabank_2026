from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from src.core.infrastructure.database.session import DbSession
from src.modules.notifications.api.dependencies import (
    CurrentViewer,
    NewsServiceDep,
    ensure_organization_visible,
)
from src.modules.notifications.api.schemas import NewsRead

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=list[NewsRead])
async def personal_news(
    request: Request,
    session: DbSession,
    viewer: CurrentViewer,
    service: NewsServiceDep,
    organization_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> list[NewsRead]:
    """News picked for the company (industry, products, legal form), each with
    the reasons in `relevance`. Without a company — general news only."""
    await ensure_organization_visible(request, session, viewer, organization_id)
    ranked = await service.personal(organization_id, limit)
    read = await service.read_ids(viewer.account_id, ranked)
    return [NewsRead.from_ranked(r, r.article.id in read) for r in ranked]


@router.post("/{news_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_news(news_id: UUID, viewer: CurrentViewer, service: NewsServiceDep) -> None:
    await service.mark_read(news_id, viewer.account_id)
