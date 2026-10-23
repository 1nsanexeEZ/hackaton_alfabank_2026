"""Screens for the frontend: the client cabinet (`/bff`) and the back office
(`/bff/backoffice`)."""

from fastapi import APIRouter

from src.modules.bff.presentation.api import backoffice, client

router = APIRouter()
router.include_router(client.router)
router.include_router(backoffice.router)
