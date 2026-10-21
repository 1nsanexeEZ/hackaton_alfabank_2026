"""Demo seeds, run on startup when SEED_DEMO_DATA=true. Every seed is
idempotent: running it twice leaves the same data.

Order matters: accounts before companies (members reference accounts),
companies and products before pre-approved offers.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed import clients, decision, identity, notifications, products
from src.core.config import Settings
from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeedContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    facades: FacadeRegistry
    clock: Clock


Seed = Callable[[SeedContext], Awaitable[None]]

SEEDS: tuple[tuple[str, Seed], ...] = (
    ("identity", identity.seed),
    ("products", products.seed),
    ("clients", clients.seed),
    ("notifications", notifications.seed),
    ("decision", decision.seed),
)


async def run_seeds(context: SeedContext) -> None:
    for name, seed in SEEDS:
        await seed(context)
        logger.info("Seed %s done", name)
