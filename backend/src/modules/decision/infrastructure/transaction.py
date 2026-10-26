"""Предодобрение вне запроса и обработчика Kafka (ночной пакет): своя сессия, хранилище,
фасады соседей и outbox на ней."""

from __future__ import annotations

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry
from src.core.messaging.outbox import OutboxWriter, SqlAlchemyOutboxWriter
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.application.ports import (
    PolicyVersionRepository,
    PreApprovalTransaction,
    PreApprovedOfferRepository,
)
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyPolicyVersionRepository,
    SqlAlchemyPreApprovedOfferRepository,
)
from src.modules.market.facade import MarketFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade

# Отправитель событий — как у подписок модуля (module.NAME).
PRODUCER = "decision"


class _Bound:
    """С чем работает одна транзакция."""

    def __init__(self, session: AsyncSession, facades: FacadeRegistry, clock: Clock) -> None:
        self.offers = SqlAlchemyPreApprovedOfferRepository(session)
        self.policy_versions = SqlAlchemyPolicyVersionRepository(session)
        self.clients = facades.get(ClientsFacade, session)
        self.products = facades.get(ProductsFacade, session)
        self.scoring = facades.get(ScoringFacade, session)
        self.market = facades.get(MarketFacade, session)
        self.outbox = SqlAlchemyOutboxWriter(session, PRODUCER, clock)


class SqlAlchemyPreApprovalTransaction(PreApprovalTransaction):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        facades: FacadeRegistry,
        clock: Clock,
    ) -> None:
        self._session_factory = session_factory
        self._facades = facades
        self._clock = clock
        self._stack = AsyncExitStack()
        self._uow: SqlAlchemyUnitOfWork | None = None
        self._bound: _Bound | None = None

    async def __aenter__(self) -> Self:
        session = await self._stack.enter_async_context(self._session_factory())
        self._uow = await self._stack.enter_async_context(SqlAlchemyUnitOfWork(session))
        self._bound = _Bound(session, self._facades, self._clock)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._uow = None
        self._bound = None
        # Откатывает незакоммиченное и закрывает сессию.
        await self._stack.__aexit__(exc_type, exc, tb)

    async def commit(self) -> None:
        await self._entered().commit()

    async def rollback(self) -> None:
        await self._entered().rollback()

    @property
    def offers(self) -> PreApprovedOfferRepository:
        return self._objects().offers

    @property
    def policy_versions(self) -> PolicyVersionRepository:
        return self._objects().policy_versions

    @property
    def clients(self) -> ClientsFacade:
        return self._objects().clients

    @property
    def products(self) -> ProductsFacade:
        return self._objects().products

    @property
    def scoring(self) -> ScoringFacade:
        return self._objects().scoring

    @property
    def market(self) -> MarketFacade:
        return self._objects().market

    @property
    def outbox(self) -> OutboxWriter:
        return self._objects().outbox

    def _objects(self) -> _Bound:
        if self._bound is None:
            raise RuntimeError("The pre-approval transaction is not entered")
        return self._bound

    def _entered(self) -> SqlAlchemyUnitOfWork:
        if self._uow is None:
            raise RuntimeError("The pre-approval transaction is not entered")
        return self._uow
