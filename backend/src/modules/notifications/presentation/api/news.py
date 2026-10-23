from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from src.modules.notifications.presentation.dependencies import (
    CurrentViewer,
    MarkNewsReadDep,
    OrganizationVisibilityDep,
    ViewerNewsDep,
)
from src.modules.notifications.presentation.schemas.news import NewsRead

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=list[NewsRead])
async def personal_news(
    viewer: CurrentViewer,
    visibility: OrganizationVisibilityDep,
    viewer_news: ViewerNewsDep,
    organization_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> list[NewsRead]:
    """News picked for the company (industry, products, legal form), each with
    the reasons in `relevance`. Without a company — general news only."""
    await visibility.execute(viewer.account_id, viewer.bank_staff, organization_id)
    news = await viewer_news.execute(viewer.account_id, organization_id, limit)
    return [NewsRead.from_dto(item) for item in news]


@router.post("/{news_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_news(news_id: UUID, viewer: CurrentViewer, mark_read: MarkNewsReadDep) -> None:
    await mark_read.execute(news_id, viewer.account_id)
