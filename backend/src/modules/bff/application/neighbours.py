"""Facades of other modules for one screen.

A screen has required blocks (the application card, the company) and optional
ones (feed, news, decision, scoring...). An optional block whose module is not
wired yet or whose source is down is left empty and named in `degraded`, the
screen is still served.

Blocks are read one after another, not with `asyncio.gather`: facades share
the request's session, and an AsyncSession does not allow concurrent queries.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from src.core.exceptions.exceptions import InfrastructureError, NotFoundError
from src.core.facades import FacadeNotRegisteredError

logger = logging.getLogger(__name__)

F = TypeVar("F")
R = TypeVar("R")

FacadeGetter = Callable[[type[Any]], Any]


class Neighbours:
    def __init__(self, get_facade: FacadeGetter) -> None:
        self._get = get_facade
        self.degraded: list[str] = []

    def __call__(self, key: type[F]) -> F:
        return self._get(key)  # type: ignore[no-any-return]

    async def optional(self, block: str, load: Callable[[], Awaitable[R]], default: R) -> R:
        """`load` looks the facade up itself, so a module that is not wired
        yet degrades the block too. NotFoundError means "no data", not a failure."""
        try:
            return await load()
        except NotFoundError:
            return default
        except FacadeNotRegisteredError as exc:
            logger.warning("bff block %r is empty: %s", block, exc)
        except InfrastructureError as exc:
            logger.warning("bff block %r is unavailable: %s", block, exc.message)
        if block not in self.degraded:
            self.degraded.append(block)
        return default
