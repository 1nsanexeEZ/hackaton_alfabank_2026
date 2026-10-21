"""Seed of clients: demo companies, members, financial reports."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from seed.run import SeedContext


async def seed(context: "SeedContext") -> None:
    """Idempotent. Implemented by the clients owner."""
