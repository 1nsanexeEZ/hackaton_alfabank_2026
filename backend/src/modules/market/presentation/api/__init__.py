from fastapi import APIRouter

from src.modules.market.presentation.api import key_rates

router = APIRouter()
router.include_router(key_rates.router)
