"""Seed of decision: pre-approved offers for demo companies."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from seed.run import SeedContext


async def seed(context: "SeedContext") -> None:
    """Idempotent. Implemented by the decision owner."""
