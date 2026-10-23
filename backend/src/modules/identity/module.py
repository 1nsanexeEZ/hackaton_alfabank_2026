"""Wiring of the identity module into the application."""

from datetime import timedelta

from fastapi import FastAPI

from src.core.access.dependencies import get_current_token
from src.core.messaging.subscriber import Subscription
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.identity.application.use_cases.bootstrap import BootstrapAdminUseCase
from src.modules.identity.facade import IdentityFacade
from src.modules.identity.infrastructure.adapters.argon2_hasher import Argon2PasswordHasher
from src.modules.identity.infrastructure.adapters.identity_facade import IdentityFacadeImpl
from src.modules.identity.infrastructure.adapters.jwt_keys import load_signing_keys
from src.modules.identity.infrastructure.adapters.jwt_token_service import JwtTokenService
from src.modules.identity.infrastructure.exception_handler import register_exception_handlers
from src.modules.identity.infrastructure.repositories.account import SqlAlchemyAccountRepository
from src.modules.identity.infrastructure.repositories.role import SqlAlchemyRoleRepository
from src.modules.identity.presentation.api import router
from src.modules.identity.presentation.dependencies import get_current_request_token

NAME = "identity"


def register(app: FastAPI) -> None:
    app.include_router(router)
    register_exception_handlers(app)


def wire(app: FastAPI) -> None:
    """The core token port and IdentityFacade are implemented here."""
    app.dependency_overrides[get_current_token] = get_current_request_token
    # The hasher is created on startup, so it's read when a facade is built;
    # the clock too: tests may swap app.state.clock.
    app.state.facades.register(
        IdentityFacade,
        lambda session: IdentityFacadeImpl(session, app.state.password_hasher, app.state.clock),
    )


async def startup(app: FastAPI) -> None:
    """Password hasher, signing keys and the bootstrap admin, before serving.
    identity goes first in MODULES, so other modules start with these in place."""
    settings = app.state.settings
    app.state.password_hasher = Argon2PasswordHasher()
    app.state.token_adapter = JwtTokenService(
        keys=load_signing_keys(
            settings.jwt_private_key_path,
            settings.jwt_public_key_path,
            generate=settings.jwt_generate_keys,
        ),
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl=timedelta(minutes=settings.jwt_access_ttl_minutes),
    )
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        async with app.state.session_factory() as session:
            bootstrap = BootstrapAdminUseCase(
                SqlAlchemyUnitOfWork(session),
                SqlAlchemyAccountRepository(session),
                SqlAlchemyRoleRepository(session),
                app.state.password_hasher,
            )
            await bootstrap.execute(
                settings.bootstrap_admin_email, settings.bootstrap_admin_password
            )


def subscribers() -> list[Subscription]:
    return []
