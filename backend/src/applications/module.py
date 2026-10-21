"""Wiring of the applications module into the application."""

import asyncio
import logging

from fastapi import FastAPI

from src.applications.api.routes import router
from src.applications.config import ApplicationsSettings
from src.applications.facade import ApplicationsFacade
from src.applications.infrastructure.edo import HttpEdoClient, SimulatedEdoClient
from src.applications.infrastructure.facade_impl import ApplicationsFacadeImpl
from src.applications.infrastructure.storage import MinioDocumentStorage
from src.core.config import Settings
from src.core.exceptions.exceptions import InfrastructureError
from src.core.messaging.subscriber import Subscription

NAME = "applications"

logger = logging.getLogger(__name__)


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    config = ApplicationsSettings()
    # Tests replace it with a fake after create_app().
    app.state.document_storage = MinioDocumentStorage(
        endpoint=settings.minio_endpoint,
        public_endpoint=settings.minio_public_endpoint or settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        bucket=settings.minio_bucket_name,
    )
    app.state.edo_client = (
        HttpEdoClient(config.external_mocks_url)
        if config.external_mocks_url
        else SimulatedEdoClient()
    )
    app.state.facades.register(
        ApplicationsFacade,
        lambda session: ApplicationsFacadeImpl(
            session, app.state.document_storage, app.state.facades
        ),
    )


async def startup(app: FastAPI) -> None:
    storage = app.state.document_storage
    if not app.state.settings.minio_ensure_bucket or not isinstance(storage, MinioDocumentStorage):
        return
    try:
        await asyncio.wait_for(storage.ensure_bucket(), timeout=15)
    except (InfrastructureError, TimeoutError):
        # Uploads answer 503 until the storage is back; the rest keeps working.
        logger.warning("Document storage is not reachable on startup")


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `applications.<purpose>`."""
    return []
