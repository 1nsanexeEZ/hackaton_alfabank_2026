"""Assembly of the use cases and the facade from the infrastructure implementations."""

from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry
from src.core.messaging.subscriber import HandlerContext
from src.modules.projector.application.use_cases.applications import (
    GetOrganizationDashboardUseCase,
    ListApplicationsUseCase,
)
from src.modules.projector.application.use_cases.metrics import GetBackofficeMetricsUseCase
from src.modules.projector.application.use_cases.project_event import ProjectEventUseCase
from src.modules.projector.application.use_cases.queue import GetUnderwritingQueueUseCase
from src.modules.projector.application.use_cases.rebuild import (
    ClearReadModelsUseCase,
    RebuildReadModelsUseCase,
    ReplayEventUseCase,
)
from src.modules.projector.application.use_cases.timeline import GetTimelineUseCase
from src.modules.projector.infrastructure.adapters.projection_transaction import (
    SqlAlchemyProjectionTransaction,
)
from src.modules.projector.infrastructure.adapters.projector_facade import ProjectorFacadeImpl
from src.modules.projector.infrastructure.repositories.read_model_queries import (
    SqlAlchemyReadModelQueries,
)
from src.modules.projector.infrastructure.repositories.read_model_store import (
    SqlAlchemyReadModelStore,
)


def projector_facade(session: AsyncSession, clock: Clock) -> ProjectorFacadeImpl:
    read_models = SqlAlchemyReadModelQueries(session)
    return ProjectorFacadeImpl(
        ListApplicationsUseCase(read_models),
        GetOrganizationDashboardUseCase(read_models),
        GetUnderwritingQueueUseCase(read_models, clock),
        GetTimelineUseCase(read_models),
        GetBackofficeMetricsUseCase(read_models),
    )


def project_event_use_case(ctx: HandlerContext) -> ProjectEventUseCase:
    """The live path: the handler's transaction is committed by the core with the inbox."""
    return ProjectEventUseCase(SqlAlchemyReadModelStore(ctx.session), ctx.facade)


def replay_event_use_case(
    session_factory: async_sessionmaker[AsyncSession], facades: FacadeRegistry
) -> ReplayEventUseCase:
    return ReplayEventUseCase(partial(SqlAlchemyProjectionTransaction, session_factory, facades))


def rebuild_use_case(
    session_factory: async_sessionmaker[AsyncSession], facades: FacadeRegistry, attempts: int = 3
) -> RebuildReadModelsUseCase:
    transactions = partial(SqlAlchemyProjectionTransaction, session_factory, facades)
    return RebuildReadModelsUseCase(
        ClearReadModelsUseCase(transactions), ReplayEventUseCase(transactions), attempts
    )
