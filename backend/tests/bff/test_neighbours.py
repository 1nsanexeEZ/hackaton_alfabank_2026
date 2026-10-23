"""FacadeNeighbours: facades bound to the request's session; an optional block
that fails is left empty and named in `degraded` once, "no data" is not a failure."""

from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.exceptions import InfrastructureError, NotFoundError
from src.core.facades import FacadeRegistry
from src.modules.bff.infrastructure.adapters.neighbours import FacadeNeighbours

SESSION = cast(AsyncSession, object())


class Source:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class NotWired:
    pass


def make_neighbours() -> FacadeNeighbours:
    registry = FacadeRegistry()
    registry.register(Source, Source)
    return FacadeNeighbours(registry, SESSION)


async def test_facade_is_bound_to_the_session() -> None:
    assert make_neighbours()(Source).session is SESSION


async def test_loaded_block_is_not_degraded() -> None:
    neighbours = make_neighbours()

    async def load() -> int:
        return 1

    assert await neighbours.optional("feed", load, 0) == 1
    assert neighbours.degraded == ()


async def test_not_found_is_no_data_not_a_failure() -> None:
    neighbours = make_neighbours()

    async def load() -> int:
        raise NotFoundError("No decision yet")

    assert await neighbours.optional("decision", load, 0) == 0
    assert neighbours.degraded == ()


async def test_not_wired_and_unavailable_blocks_are_degraded_once() -> None:
    neighbours = make_neighbours()

    async def not_wired() -> int:
        neighbours(NotWired)
        return 1

    async def unavailable() -> int:
        raise InfrastructureError("Source is down")

    assert await neighbours.optional("decision", not_wired, 0) == 0
    assert await neighbours.optional("feed", unavailable, 0) == 0
    assert await neighbours.optional("feed", unavailable, 0) == 0
    assert neighbours.degraded == ("decision", "feed")
