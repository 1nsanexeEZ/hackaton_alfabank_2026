import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed import identity
from seed.run import SeedContext
from src.core.config import Settings
from src.core.domain.clock import SystemClock
from src.core.facades import FacadeRegistry

DEMO_PASSWORD = "Demo-password-1"


def seed_context(session_factory: async_sessionmaker[AsyncSession]) -> SeedContext:
    return SeedContext(
        settings=Settings(_env_file=None, demo_password=DEMO_PASSWORD),
        session_factory=session_factory,
        facades=FacadeRegistry(),
        clock=SystemClock(),
    )


@pytest.fixture
async def seeded(
    session_factory: async_sessionmaker[AsyncSession],
) -> async_sessionmaker[AsyncSession]:
    """Bare database with the identity seed applied once."""
    await identity.seed(seed_context(session_factory))
    return session_factory
