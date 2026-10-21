"""Seed of products: product catalog."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from seed.run import SeedContext


async def seed(context: "SeedContext") -> None:
    """Idempotent. Implemented by the products owner."""
