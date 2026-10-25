"""Use cases for the routers: adapters are picked here, use cases see only interfaces."""

from decimal import Decimal
from typing import Annotated

from fastapi import Depends, Request

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.core.uow import SqlAlchemyUnitOfWork, UnitOfWork
from src.modules.market.application.interfaces.repositories import KeyRateRepository
from src.modules.market.application.use_cases.key_rates import (
    AddKeyRateUseCase,
    GetKeyRateUseCase,
    ListKeyRatesUseCase,
    RemoveKeyRateUseCase,
)
from src.modules.market.infrastructure.repositories.key_rates import SqlAlchemyKeyRateRepository

# --- access --------------------------------------------------------------------

# As the versions of the credit policy: the key rate prices every offer.
CanRead = [Depends(require_permissions(Permissions.SCORING_READ))]
Editor = Annotated[OpenSubTokenDTO, Depends(require_permissions(Permissions.SCORING_UPDATE))]


# --- adapters ------------------------------------------------------------------


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_fallback(request: Request) -> Decimal:
    key_rate: Decimal = request.app.state.settings.key_rate
    return key_rate


def get_uow(session: DbSession) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def get_repository(session: DbSession) -> KeyRateRepository:
    return SqlAlchemyKeyRateRepository(session)


ClockDep = Annotated[Clock, Depends(get_clock)]
Fallback = Annotated[Decimal, Depends(get_fallback)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Repository = Annotated[KeyRateRepository, Depends(get_repository)]


# --- use cases -----------------------------------------------------------------


def get_get_key_rate(
    repository: Repository, clock: ClockDep, fallback: Fallback
) -> GetKeyRateUseCase:
    return GetKeyRateUseCase(repository, clock, fallback)


def get_list_key_rates(
    repository: Repository, clock: ClockDep, fallback: Fallback
) -> ListKeyRatesUseCase:
    return ListKeyRatesUseCase(repository, clock, fallback)


def get_add_key_rate(uow: Uow, repository: Repository, clock: ClockDep) -> AddKeyRateUseCase:
    return AddKeyRateUseCase(uow, repository, clock)


def get_remove_key_rate(uow: Uow, repository: Repository, clock: ClockDep) -> RemoveKeyRateUseCase:
    return RemoveKeyRateUseCase(uow, repository, clock)


GetKeyRateDep = Annotated[GetKeyRateUseCase, Depends(get_get_key_rate)]
ListKeyRatesDep = Annotated[ListKeyRatesUseCase, Depends(get_list_key_rates)]
AddKeyRateDep = Annotated[AddKeyRateUseCase, Depends(get_add_key_rate)]
RemoveKeyRateDep = Annotated[RemoveKeyRateUseCase, Depends(get_remove_key_rate)]
