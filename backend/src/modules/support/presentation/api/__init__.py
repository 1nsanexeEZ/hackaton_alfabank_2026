from fastapi import APIRouter

from src.modules.support.presentation.api import client, staff

router = APIRouter()
router.include_router(client.router)
router.include_router(staff.router)
