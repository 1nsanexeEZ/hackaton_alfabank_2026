from fastapi import APIRouter

from src.identity.api import accounts, auth, me, roles

router = APIRouter()
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(accounts.router)
router.include_router(roles.router)
