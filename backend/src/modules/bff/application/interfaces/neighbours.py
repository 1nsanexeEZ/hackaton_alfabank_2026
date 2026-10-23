"""Facades of other modules for one screen.

A screen has required blocks (the application card, the company) and optional
ones (feed, news, decision, scoring...). An optional block whose module is not
wired yet or whose source is down is left empty and named in `degraded`, the
screen is still served.

Blocks are read one after another, not with `asyncio.gather`: facades share
the request's session, and an AsyncSession does not allow concurrent queries.
"""

from collections.abc import Awaitable, Callable
from typing import Protocol


class Neighbours(Protocol):
    def __call__[F](self, key: type[F]) -> F:
        """The facade of a neighbour; one that is not wired raises."""
        ...

    async def optional[R](self, block: str, load: Callable[[], Awaitable[R]], default: R) -> R:
        """`load` looks the facade up itself, so a module that is not wired
        yet degrades the block too. NotFoundError means "no data", not a failure."""
        ...

    @property
    def degraded(self) -> tuple[str, ...]:
        """Optional blocks left empty so far, in the order they failed."""
        ...
