from dataclasses import replace

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed.products import catalog, seed
from seed.run import SeedContext
from src.core.config import Settings
from src.core.domain import FrozenClock
from src.core.facades import FacadeRegistry
from src.products.application.mappers import product_dto
from src.products.domain.product import ProductStatus
from src.products.infrastructure.models import CreditProductRecord
from src.products.infrastructure.repository import SqlAlchemyProductRepository

Sessions = async_sessionmaker[AsyncSession]


async def run_seed(session_factory: Sessions) -> None:
    context = SeedContext(
        Settings(_env_file=None), session_factory, FacadeRegistry(), FrozenClock()
    )
    await seed(context)


async def test_seed_is_idempotent(session_factory: Sessions) -> None:
    await run_seed(session_factory)
    async with session_factory() as session:
        first = [product_dto(p) for p in await SqlAlchemyProductRepository(session).list_active()]

    await run_seed(session_factory)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(CreditProductRecord))
        again = [product_dto(p) for p in await SqlAlchemyProductRepository(session).list_active()]

    assert count == 8
    assert again == first


async def test_round_trip_keeps_every_field(session_factory: Sessions) -> None:
    await run_seed(session_factory)
    async with session_factory() as session:
        repository = SqlAlchemyProductRepository(session)
        stored = {p.code.value: product_dto(p) for p in await repository.list_active()}
    assert list(stored) == [p.code.value for p in catalog()]
    for product in catalog():
        assert stored[product.code.value] == product_dto(product), product.code


async def test_drafts_are_not_current_and_archived_stay_readable(session_factory: Sessions) -> None:
    await run_seed(session_factory)
    unsecured = next(p for p in catalog() if p.code.value == "UNSECURED")
    async with session_factory() as session:
        repository = SqlAlchemyProductRepository(session)
        await repository.save(replace(unsecured, version=2, status=ProductStatus.DRAFT))
        await session.commit()
        current = await repository.get_current("UNSECURED")
        assert current is not None and current.version == 1

        unsecured.archive()
        await repository.save(unsecured)
        await session.commit()
        current = await repository.get_current("UNSECURED")
        assert current is not None and current.status == ProductStatus.ARCHIVED
        assert "UNSECURED" not in [p.code.value for p in await repository.list_active()]

        draft = await repository.get_version("UNSECURED", 2)
        assert draft is not None
        draft.activate()
        await repository.save(draft)
        await session.commit()
        current = await repository.get_current("UNSECURED")
        assert current is not None and (current.version, current.status) == (2, "active")
        listed = [p for p in await repository.list_active() if p.code.value == "UNSECURED"]
        assert [p.version for p in listed] == [2]


async def test_unknown_product(session_factory: Sessions) -> None:
    async with session_factory() as session:
        repository = SqlAlchemyProductRepository(session)
        assert await repository.get_current("NOPE") is None
        assert await repository.get_version("NOPE", 1) is None
