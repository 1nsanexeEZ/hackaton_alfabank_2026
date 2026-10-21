from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import src.models  # noqa: F401  registers every table
from src.core.config import Settings
from src.core.infrastructure.database.base import Base
from src.main import create_app
from tests.helpers import create_schema

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin-password-1"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        jwt_private_key_path=tmp_path / "keys" / "private.pem",
        jwt_public_key_path=tmp_path / "keys" / "public.pem",
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=ADMIN_PASSWORD,
        messaging_mode="manual",
        minio_ensure_bucket=False,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    create_schema(settings.database_url)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def login(client: TestClient) -> Callable[[str, str], str]:
    def do_login(login_value: str, password: str) -> str:
        response = client.post("/auth/login", json={"login": login_value, "password": password})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return do_login


@pytest.fixture
def admin_token(login: Callable[[str, str], str]) -> str:
    return login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Bare database with every table, for repository and messaging tests."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'unit.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
