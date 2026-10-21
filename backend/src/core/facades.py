"""Registry of module facades.

A module reads another module only through its facade (`src/<module>/facade.py`):
a Protocol plus frozen DTOs. The owner registers the implementation in its
`module.wire(app)`; consumers get it by the Protocol type:

    # HTTP
    clients: Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]
    # Kafka handler
    clients = ctx.facade(ClientsFacade)

Implementations are built per session, so a facade call joins the caller's
transaction. Tests register fakes from `tests/fakes` the same way.
"""

from collections.abc import Callable
from typing import Annotated, Any, TypeVar, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.infrastructure.database.session import get_session

T = TypeVar("T")

FacadeFactory = Callable[[AsyncSession], Any]


class FacadeNotRegisteredError(LookupError):
    pass


class FacadeRegistry:
    def __init__(self) -> None:
        self._factories: dict[type[Any], FacadeFactory] = {}

    def register(self, key: type[T], factory: Callable[[AsyncSession], T]) -> None:
        self._factories[key] = factory

    def has(self, key: type[Any]) -> bool:
        return key in self._factories

    def get(self, key: type[T], session: AsyncSession) -> T:
        try:
            factory = self._factories[key]
        except KeyError:
            raise FacadeNotRegisteredError(
                f"Facade {key.__name__} is not registered: the owning module must call "
                f"app.state.facades.register({key.__name__}, ...) in its module.wire(app)"
            ) from None
        return cast(T, factory(session))


def get_facade_registry(request: Request) -> FacadeRegistry:
    return cast(FacadeRegistry, request.app.state.facades)


def use_facade[F](key: type[F]) -> Callable[[Request, AsyncSession], F]:
    """FastAPI dependency factory: `Depends(use_facade(ClientsFacade))`."""

    def dependency(
        request: Request,
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> F:
        return get_facade_registry(request).get(key, session)

    dependency.__name__ = f"use_{key.__name__}"
    return dependency
