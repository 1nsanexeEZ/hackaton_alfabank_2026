from fastapi import APIRouter

from src.modules.identity.presentation.api import (
    accounts,
    auth,
    me,
    organization_consents,
    roles,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(organization_consents.router)
router.include_router(accounts.router)
router.include_router(roles.router)
