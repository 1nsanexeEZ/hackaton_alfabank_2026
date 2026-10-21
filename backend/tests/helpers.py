import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.access.permissions import Permissions
from src.models import metadata


async def wait_for(
    condition: Callable[[], Awaitable[bool]], seconds: float = 5.0, interval: float = 0.05
) -> None:
    """Poll an async condition until it holds (integration and e2e tests)."""
    try:
        async with asyncio.timeout(seconds):
            while True:
                if await condition():
                    return
                await asyncio.sleep(interval)
    except TimeoutError:
        raise TimeoutError(f"Condition not met in {seconds} s") from None


def token_for(
    app: FastAPI,
    permissions: list[Permissions | str],
    policies: dict[Permissions | str, list[str]] | None = None,
    subject: UUID | None = None,
) -> str:
    """Access token signed with the app's key; the app must be started
    (inside `TestClient(app)` context)."""
    issued = app.state.token_adapter.issue(
        subject or uuid4(),
        [str(p) for p in permissions],
        {str(k): v for k, v in (policies or {}).items()},
    )
    return issued.access_token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_schema(database_url: str) -> None:
    """All tables straight from the models (tests run on SQLite, not migrations)."""

    async def create() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        await engine.dispose()

    asyncio.run(create())
