"""Facades of other modules from the registry, bound to the request's session."""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.exceptions import InfrastructureError, NotFoundError
from src.core.facades import FacadeNotRegisteredError, FacadeRegistry
from src.modules.bff.application.interfaces.neighbours import Neighbours

logger = logging.getLogger(__name__)


class FacadeNeighbours(Neighbours):
    def __init__(self, registry: FacadeRegistry, session: AsyncSession) -> None:
        self._registry = registry
        self._session = session
        self._degraded: list[str] = []

    def __call__[F](self, key: type[F]) -> F:
        return self._registry.get(key, self._session)

    @property
    def degraded(self) -> tuple[str, ...]:
        return tuple(self._degraded)

    async def optional[R](self, block: str, load: Callable[[], Awaitable[R]], default: R) -> R:
        try:
            return await load()
        except NotFoundError:
            return default
        except FacadeNotRegisteredError as exc:
            logger.warning("bff block %r is empty: %s", block, exc)
        except InfrastructureError as exc:
            logger.warning("bff block %r is unavailable: %s", block, exc.message)
        if block not in self._degraded:
            self._degraded.append(block)
        return default
