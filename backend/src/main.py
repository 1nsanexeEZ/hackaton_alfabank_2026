from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from src.core.access.dependencies import get_current_token
from src.core.config import Settings, get_settings
from src.core.exceptions.handlers import register_exception_handlers
from src.core.infrastructure.database.session import build_engine, build_session_factory
from src.identity.api import router as identity_router
from src.identity.bootstrap import bootstrap_admin
from src.identity.dependencies import get_current_request_token
from src.identity.keys import load_signing_keys
from src.identity.passwords import PasswordHasher
from src.identity.token_adapter import TokenAdapter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine = build_engine(settings.database_url)
        app.state.session_factory = build_session_factory(engine)
        app.state.password_hasher = PasswordHasher()
        app.state.token_adapter = TokenAdapter(
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
            await bootstrap_admin(
                app.state.session_factory,
                app.state.password_hasher,
                settings.bootstrap_admin_email,
                settings.bootstrap_admin_password,
            )
        yield
        await engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_exception_handlers(app)

    app.include_router(identity_router)
    app.dependency_overrides[get_current_token] = get_current_request_token

    @app.get("/health", tags=["service"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
