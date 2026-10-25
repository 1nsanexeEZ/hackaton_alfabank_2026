"""Wiring of the applications module into the application."""

import asyncio
import logging

from fastapi import FastAPI

from src.core.config import Settings
from src.core.exceptions.exceptions import InfrastructureError
from src.core.messaging.subscriber import Subscription
from src.modules.applications.application.interfaces.abs import AbsClient
from src.modules.applications.facade import ApplicationsFacade
from src.modules.applications.infrastructure.adapters.abs_client import (
    HttpAbsClient,
    SimulatedAbsClient,
)
from src.modules.applications.infrastructure.adapters.contract_archive import (
    MinioContractArchive,
)
from src.modules.applications.infrastructure.adapters.contract_sealer import (
    PyHankoContractSealer,
)
from src.modules.applications.infrastructure.adapters.document_storage import (
    MinioDocumentStorage,
)
from src.modules.applications.infrastructure.adapters.edo_client import (
    HttpEdoClient,
    SimulatedEdoClient,
)
from src.modules.applications.infrastructure.config import ApplicationsSettings
from src.modules.applications.infrastructure.contract_pdf.renderer import FpdfContractRenderer
from src.modules.applications.presentation.api.applications import router
from src.modules.applications.presentation.api.contracts import router as contracts_router
from src.modules.applications.presentation.consumers import subscriptions
from src.modules.applications.presentation.dependencies import applications_facade
from src.modules.applications.presentation.expiry import run_offer_expiry

NAME = "applications"

logger = logging.getLogger(__name__)


def register(app: FastAPI) -> None:
    app.include_router(router)
    app.include_router(contracts_router)


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
    # Contract PDFs: tests replace the archive with a fake after create_app().
    app.state.contract_archive = MinioContractArchive(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        bucket=config.contracts_bucket,
        retention_days=config.contracts_retention_days,
    )
    # The demo CA keys live next to the JWT keys (the `jwt-keys` volume in docker).
    app.state.contract_sealer = PyHankoContractSealer(settings.jwt_private_key_path.parent)
    app.state.contract_renderer = FpdfContractRenderer()
    # The site address people see: QR codes of the contracts lead to its /verify page.
    app.state.public_base_url = settings.minio_public_endpoint or "http://localhost:8080"
    app.state.edo_client = (
        HttpEdoClient(config.external_mocks_url)
        if config.external_mocks_url
        else SimulatedEdoClient()
    )
    app.state.applications_config = config
    abs_client = (
        HttpAbsClient(config.external_mocks_url)
        if config.external_mocks_url
        else SimulatedAbsClient()
    )
    # Module-private port for the Kafka handlers (they get ports from the registry).
    app.state.facades.register(AbsClient, lambda _session: abs_client)
    app.state.facades.register(
        ApplicationsFacade,
        lambda session: applications_facade(session, app.state.document_storage, app.state.facades),
    )


async def startup(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    storage = app.state.document_storage
    if settings.minio_ensure_bucket and isinstance(storage, MinioDocumentStorage):
        try:
            await asyncio.wait_for(storage.ensure_bucket(), timeout=15)
        except (InfrastructureError, TimeoutError):
            # Uploads answer 503 until the storage is back; the rest keeps working.
            logger.warning("Document storage is not reachable on startup")
    archive = app.state.contract_archive
    if settings.minio_ensure_bucket and isinstance(archive, MinioContractArchive):
        try:
            await asyncio.wait_for(archive.ensure_bucket(), timeout=15)
        except (InfrastructureError, TimeoutError):
            logger.warning("Contract archive is not reachable on startup")
    if settings.run_background_jobs:
        stop = asyncio.Event()
        app.state.applications_jobs = (
            stop,
            asyncio.create_task(
                run_offer_expiry(
                    app.state.session_factory,
                    app.state.clock,
                    stop,
                    app.state.applications_config.offer_expiry_interval_seconds,
                ),
                name="applications-offer-expiry",
            ),
        )


async def shutdown(app: FastAPI) -> None:
    jobs = getattr(app.state, "applications_jobs", None)
    if jobs is not None:
        stop, task = jobs
        stop.set()
        await task


def subscribers() -> list[Subscription]:
    """Commands of the process; stage labels from process events."""
    return subscriptions()
