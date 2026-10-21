from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from seed.run import SeedContext, run_seeds
from src.applications import module as applications_module
from src.bff import module as bff_module
from src.clients import module as clients_module
from src.core.config import Settings, get_settings
from src.core.domain.clock import Clock, SystemClock
from src.core.exceptions.handlers import register_exception_handlers
from src.core.facades import FacadeRegistry
from src.core.http.request_id import RequestIdMiddleware, configure_logging
from src.core.infrastructure.database.session import build_engine, build_session_factory
from src.core.messaging.runtime import MessagingRuntime
from src.decision import module as decision_module
from src.enrichment import module as enrichment_module
from src.identity import module as identity_module
from src.identity.bootstrap import bootstrap_admin
from src.identity.keys import load_signing_keys
from src.identity.passwords import PasswordHasher
from src.identity.token_adapter import TokenAdapter
from src.notifications import module as notifications_module
from src.process import module as process_module
from src.products import module as products_module
from src.projector import module as projector_module
from src.scoring import module as scoring_module

# Explicit list: no discovery by string. Each module owns only its module.py.
MODULES = (
    identity_module,
    products_module,
    clients_module,
    applications_module,
    process_module,
    enrichment_module,
    scoring_module,
    decision_module,
    notifications_module,
    projector_module,
    bff_module,
)


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or get_settings()
    clock = clock or SystemClock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        configure_logging()
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
        if settings.seed_demo_data:
            await run_seeds(
                SeedContext(settings, app.state.session_factory, app.state.facades, clock)
            )

        messaging = MessagingRuntime(
            settings,
            app.state.session_factory,
            app.state.facades,
            clock,
            [subscription for module in MODULES for subscription in module.subscribers()],
        )
        await messaging.start()
        app.state.messaging = messaging
        try:
            yield
        finally:
            await messaging.stop()
            await engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = clock
    # Filled by module.wire(); tests may register fakes after create_app().
    app.state.facades = FacadeRegistry()
    register_exception_handlers(app)
    app.add_middleware(RequestIdMiddleware)

    for module in MODULES:
        module.register(app)
    for module in MODULES:
        module.wire(app)

    @app.get("/health", tags=["service"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["service"])
    async def ready() -> JSONResponse:
        checks: dict[str, str] = {}
        try:
            async with app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "unavailable"
        broker = app.state.messaging.broker
        if broker is not None:
            checks["kafka"] = "ok" if await broker.ping(timeout=2.0) else "unavailable"
        healthy = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ok" if healthy else "unavailable", "checks": checks},
        )

    return app


app = create_app()
