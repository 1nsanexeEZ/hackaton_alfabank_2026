from fastapi import APIRouter

from src.notifications.api import feed, news

router = APIRouter()
router.include_router(feed.router)
router.include_router(news.router)
